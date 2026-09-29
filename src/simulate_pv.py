"""PV simulator – impact of a shared/community PV share (0–6 kWp) on Aleksandra's grid purchases, costs and payback,
without (A) and with (B) shifting washer, dishwasher and hot water to the best hours. Logic: src/hackowatt/pv.py.

Writes data/app/pv_simulation.json (for the app) and prints a comparison table.

Usage:  python src/simulate_pv.py             # downloads the PVGIS series once (cached in data/weather/)
        python src/simulate_pv.py --offline   # only use the cached PVGIS file
"""
import argparse
import json

from hackowatt.paths import ROOT
from hackowatt.pv import simulate

OUT = ROOT / "data" / "app" / "pv_simulation.json"


def main():
    ap = argparse.ArgumentParser(description="PV simulator (scenarios A and B)")
    ap.add_argument("--offline", action="store_true", help="use the cached PVGIS file only")
    args = ap.parse_args()
    meta, results = simulate(offline=args.offline)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(meta=meta, sizes=results), indent=2, ensure_ascii=False) + "\n")

    print(f"Year {meta['year']}: consumption {meta['consumption_kwh']} kWh, cost without PV €{meta['cost_without_pv']:.2f}")
    print(f"PV yield {meta['yield_kwh_per_kwp']} kWh/kWp ({meta['source']})\n")
    head = f"{'kWp':>3} {'invest':>7} {'produced':>9} │ {'covered':>7} {'grid kWh':>8} {'saving/yr':>9} {'payback':>8} │ " \
           f"{'covered':>7} {'grid kWh':>8} {'saving/yr':>9} {'payback':>8}"
    print(f"{'':30}│ {'A – no habit change':^44}│ {'B – with shifting':^44}")
    print(head)
    for r in results:
        cells = []
        for s in ("A", "B"):
            x = r[s]
            pb = f"{x['payback_years']:.1f} y" if x["payback_years"] else "–"
            cells.append(f"{x['self_sufficiency']:>7.0%} {(-x['grid_reduction'] or 0.0):>8.0f} {x['saving']:>8.0f}€ {pb:>8}")
        print(f"{r['kwp']:>3} {r['investment']:>6.0f}€ {r['production']:>7.0f}kWh │ {cells[0]} │ {cells[1]}")
    print(f"\ncovered = share of her consumption supplied by her PV share · grid kWh = change in kWh/year bought from the grid"
          f"\nsaving/yr = vs. today, after the 1 % operating cost · wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
