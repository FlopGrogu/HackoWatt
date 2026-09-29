"""Validation report: year-overview figures and a check of the appliance parameters against the scenario's table (page 3)."""
import csv
from collections import defaultdict
from datetime import datetime

import numpy as np

GROUPS = [("Space heating", ["heat_pump_space_heating"], "#0072B2"), ("Hot water", ["heat_pump_hot_water"], "#D55E00"),
          ("Always on (fridge, router, standby)", ["fridge", "wifi_router", "standby"], "#7f7f7f"),
          ("Activities (kitchen, laundry, TV, laptop, lights, charging)", ["kettle", "coffee_machine", "oven", "washing_machine", "dishwasher", "tv",
                                                                      "laptop", "lighting", "phone_tablet_charging"], "#E69F00")]
INK, MUTED = "#222222", "#666666"


def _load(cfg):
    rows = list(csv.DictReader(open(cfg.data / "consumption" / "hourly_consumption.csv")))
    t = [datetime.fromisoformat(r["timestamp"][:16]) for r in rows]
    col = lambda k: np.array([float(r[k]) for r in rows])
    return rows, t, col


def figures(cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": "#e6e6e6", "grid.linewidth": 0.6})
    out = cfg.data / "consumption" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    rows, t, col = _load(cfg)
    H = len(rows)
    days = H // 24
    grp = [sum(col(f"{a}_kwh") for a in apps) for _, apps, _ in GROUPS]
    daily = [g[: days * 24].reshape(days, 24).sum(1) for g in grp]
    temp = col("temp_out_c")[: days * 24].reshape(days, 24).mean(1)
    away = np.array([r["occupancy"] in ("away", "Paul only") for r in rows], float)[: days * 24].reshape(days, 24).mean(1)
    x = np.arange(days)
    ticks = [i for i, d in enumerate(t[::24]) if d.day == 1]
    labels = [t[i * 24].strftime("%b") for i in ticks]

    fig, ax = plt.subplots(3, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1.2, 1.2]})
    bottom = np.zeros(days)
    for (name, _, color), d in zip(GROUPS, daily):
        ax[0].bar(x, d, bottom=bottom, width=1.0, color=color, label=name, linewidth=0)
        bottom += d
    ax[0].set_ylabel("kWh per day")
    ax[0].set_title(f"Aleksandra {cfg.year}: daily electricity use", loc="left", fontweight="bold", color=INK)
    ax[0].legend(loc="upper center", ncol=2, frameon=False, fontsize=8)
    ax[1].plot(x, temp, color="#0072B2", linewidth=1.4)
    ax[1].axhline(0, color=MUTED, linewidth=0.6)
    ax[1].set_ylabel("outdoor °C (daily mean)")
    ax[2].bar(x, away * 100, width=1.0, color="#7f7f7f", linewidth=0)
    ax[2].set_ylabel("away, % of day")
    ax[2].set_ylim(0, 100)
    ax[2].set_xticks(ticks)
    ax[2].set_xticklabels(labels)
    fig.tight_layout()
    fig.savefig(out / "year_overview.png", dpi=150)
    plt.close(fig)

    # one week per season
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), sharey=True)
    for a, (month, name) in zip(axes.ravel(), ((1, "Winter (Jan)"), (4, "Spring (Apr)"), (7, "Summer (Jul)"), (10, "Autumn (Oct)"))):
        i0 = next(i for i, d in enumerate(t) if d.month == month and d.day == 12 and d.hour == 0)
        sl = slice(i0, i0 + 168)
        xs = np.arange(168)
        b = np.zeros(168)
        for (gname, _, color), g in zip(GROUPS, grp):
            a.bar(xs, g[sl], bottom=b, width=1.0, color=color, linewidth=0)
            b += g[sl]
        for k in range(168):
            if rows[i0 + k]["occupancy"] == "away":
                a.axvspan(k - 0.5, k + 0.5, ymin=0, ymax=0.04, color="#333333", linewidth=0)
        a.set_title(f"{name}: {t[i0]:%d %b}–{t[i0 + 167]:%d %b}, mean {col('temp_out_c')[sl].mean():.1f} °C  (dark strip = away)", loc="left", fontsize=9, color=INK)
        a.set_xticks(range(0, 168, 24))
        a.set_xticklabels([t[i0 + k].strftime("%a") for k in range(0, 168, 24)])
        a.set_ylabel("kWh per hour")
    fig.tight_layout()
    fig.savefig(out / "season_weeks.png", dpi=150)
    plt.close(fig)

    # mean daily profile, home vs away, per season
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    tot = col("total_kwh")
    occ = np.array([r["occupancy"] for r in rows])
    hour = np.array([d.hour for d in t])
    month = np.array([d.month for d in t])
    for a, (months, name) in zip(axes, (((12, 1, 2), "Winter"), ((3, 4, 5), "Spring"), ((6, 7, 8), "Summer"), ((9, 10, 11), "Autumn"))):
        sel = np.isin(month, months)
        for label, mask, color in (("home", occ != "away", "#0072B2"), ("away", occ == "away", "#D55E00")):
            m = sel & mask
            a.plot(range(24), [tot[m & (hour == h)].mean() if (m & (hour == h)).any() else np.nan for h in range(24)], color=color, linewidth=1.8, label=label)
        a.set_title(name, loc="left", color=INK)
        a.set_xlabel("hour of day")
        a.set_xticks(range(0, 24, 6))
    axes[0].set_ylabel("mean kWh per hour")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "daily_profile_by_season.png", dpi=150)
    plt.close(fig)

    # geolocation
    pos = list(csv.DictReader(open(cfg.data / "geolocation" / "positions.csv")))
    lat = np.array([float(r["lat"]) for r in pos])
    lon = np.array([float(r["lon"]) for r in pos])
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.5))
    ax[0].scatter(lon, lat, s=2, color="#0072B2", alpha=0.35, linewidths=0)
    ax[0].scatter([cfg.home[1]], [cfg.home[0]], s=40, color="#D55E00", zorder=3)
    ax[0].set_title(f"All {len(pos):,} fixes of {cfg.year} (orange = home)", loc="left", color=INK)
    ax[0].set_xlabel("longitude")
    ax[0].set_ylabel("latitude")
    near = (abs(lat - cfg.lat) < 0.09) & (abs(lon - cfg.lon) < 0.14)
    ax[1].scatter(lon[near], lat[near], s=3, color="#0072B2", alpha=0.35, linewidths=0)
    ax[1].scatter([cfg.home[1]], [cfg.home[0]], s=40, color="#D55E00", zorder=3)
    ax[1].set_title(f"{cfg.city} zoom", loc="left", color=INK)
    ax[1].set_xlabel("longitude")
    fig.tight_layout()
    fig.savefig(out / "geolocation.png", dpi=150)
    plt.close(fig)
    return out


def validation(cfg, sim, itin):
    """Compare the simulated appliances with the scenario table; returns markdown."""
    log = defaultdict(list)
    for e in sim.log:
        log[e["appliance"]].append(e)
    days = sim.N / 1440
    dur = lambda es: [(e["end"] - e["start"]).total_seconds() / 60 for e in es]
    daily = {a: sim.loads[a].sum() / 60 / days for a in sim.loads}
    L = []

    def line(name, spec, got, ok):
        L.append(f"| {name} | {spec} | {got} | {'ok' if ok else '**CHECK**'} |")

    L += ["| Appliance | Scenario range | Simulated | |", "|---|---|---|---|"]
    fr = daily["fridge"]
    line("Refrigerator", "0.8–1.2 kWh/day", f"{fr:.2f} kWh/day", 0.8 <= fr <= 1.25)
    hp = np.concatenate([sim.loads["heat_pump_space_heating"][sim.loads["heat_pump_space_heating"] > 0]])
    line("Heat pump (space heating)", "1.0–3.0 kW in operation", f"{hp.min():.2f}–{hp.max():.2f} kW", hp.min() >= 0.99 and hp.max() <= 3.01)
    k = dur(log["kettle"])
    line("Kettle", "2.0 kW, 3–5 min/use", f"2.0 kW, {min(k):.0f}–{max(k):.0f} min", min(k) >= 3 and max(k) <= 5)
    c = dur(log["coffee_machine"])
    cp = [e["peak_kw"] for e in log["coffee_machine"]]
    line("Coffee machine", "1.0–1.5 kW, 5–10 min", f"{min(cp):.2f}–{max(cp):.2f} kW, {min(c):.0f}–{max(c):.0f} min", min(cp) >= 1 and max(cp) <= 1.5 and min(c) >= 5 and max(c) <= 10)
    op = [e["peak_kw"] for e in log["oven"]]
    line("Oven", "2.0–2.5 kW", f"{min(op):.2f}–{max(op):.2f} kW", min(op) >= 2 and max(op) <= 2.5)
    w = [e["kwh"] for e in log["washing_machine"] if e["kwh"] > 0.3]
    line("Washing machine", "0.6–1.0 kWh/cycle", f"{min(w):.2f}–{max(w):.2f} kWh ({len(w)} cycles)", min(w) >= 0.59 and max(w) <= 1.01)
    dw = [e["kwh"] for e in log["dishwasher"]]
    line("Dishwasher", "0.8–1.2 kWh/cycle", f"{min(dw):.2f}–{max(dw):.2f} kWh ({len(dw)} cycles)", min(dw) >= 0.79 and max(dw) <= 1.21)
    tv = [e["peak_kw"] for e in log["tv"]]
    line("Television", "0.08–0.15 kW", f"{min(tv):.3f}–{max(tv):.3f} kW", min(tv) >= 0.079 and max(tv) <= 0.151)
    lp = sim.loads["laptop"][sim.loads["laptop"] > 0]
    line("Laptop", "0.04–0.08 kW", f"{lp.min():.3f}–{lp.max():.3f} kW", lp.min() >= 0.039 and lp.max() <= 0.081)
    r = sim.loads["wifi_router"]
    line("Wi-Fi router", "0.008–0.015 kW continuous", f"{r.min():.4f}–{r.max():.4f} kW", r.min() >= 0.008 and r.max() <= 0.015)
    lg = sim.loads["lighting"][sim.loads["lighting"] > 0]
    dark = lg[lg >= 0.045]
    line("Lighting", "0.05–0.15 kW when active", f"{dark.min():.3f}–{dark.max():.3f} kW (+ 30 W on very cloudy days)", dark.min() >= 0.049 and dark.max() <= 0.151)
    ch = [e["kwh"] for e in log["phone_tablet_charging"]]
    line("Phone / tablet charging", "0.005–0.02 kWh/device/charge", f"{min(ch):.3f}–{max(ch):.3f} kWh per charge", max(ch) <= 0.0201)
    sb = sim.loads["standby"]
    line("Standby", "0.02–0.06 kW combined", f"{sb.min():.3f}–{sb.max():.3f} kW", sb.min() >= 0.015 and sb.max() <= 0.061)
    away = itin.away
    L += ["", "| Check | Result |", "|---|---|",
          f"| Share of the year away from the flat | {away.mean():.1%} |",
          f"| Nights away from home | {sum(t.nights for t in itin.trips)} on {len([t for t in itin.trips if t.nights >= 1])} trips (+ {len([t for t in itin.trips if t.nights == 0])} day trips) |",
          f"| Yearly consumption | {sim.total.sum():.0f} kWh ({sim.total.sum() / days:.1f} kWh/day) |",
          f"| Heating | {sim.hourly['heat_pump_space_heating'].sum():.0f} kWh, hot water {sim.hourly['heat_pump_hot_water'].sum():.0f} kWh |",
          f"| Indoor temperature | {sim.T_IN.min():.1f}–{sim.T_IN.max():.1f} °C (mean {sim.T_IN.mean():.1f}) |"]
    monthly = defaultdict(float)
    for h, tt in enumerate(sim.w.times):
        monthly[tt.month] += sim.total[h]
    L += ["", "| Month | kWh | mean outdoor °C |", "|---|---|---|"]
    for m in range(1, 13):
        temps = [sim.w.temp[h] for h, tt in enumerate(sim.w.times) if tt.month == m]
        L.append(f"| {datetime(2000, m, 1):%b} | {monthly[m]:.0f} | {sum(temps) / len(temps):.1f} |")
    text = "\n".join(L) + "\n"
    (cfg.data / "consumption" / "validation.md").write_text(f"# Generated data vs the scenario's appliance table (seed {cfg.seed})\n\n" + text)
    return text
