import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime

# Setup paths and styling
ROOT = Path(__file__).resolve().parent.parent if "__file__" in locals() else Path.cwd().parent
DATA_DIR = ROOT / "data" / "consumption"
FIG_DIR = DATA_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")
plt.rcParams.update({"figure.autolayout": True, "font.size": 10})

# Load datasets
hourly_df = pd.read_csv(DATA_DIR / "hourly_consumption.csv", parse_dates=["timestamp"])
events_df = pd.read_csv(DATA_DIR / "appliance_events.csv", parse_dates=["start", "end"])

# Cutoff date for history vs future prediction (Day 30 / Sept 29, 2026)
PREDICTION_CUTOFF = datetime(2026, 9, 29)

# Define appliance list
APPLIANCES = [
    "fridge", "heat_pump_space_heating", "heat_pump_hot_water", "kettle", 
    "coffee_machine", "oven", "washing_machine", "dishwasher", "tv", 
    "laptop", "wifi_router", "lighting", "phone_tablet_charging", "standby"
]

print(f"Loaded {len(hourly_df)} hourly records and {len(events_df)} appliance events.")

# =====================================================================================
# 1. Daily Energy Consumption Breakdown (Stacked Bar Chart with Red Cutoff Line)
# =====================================================================================
def plot_daily_breakdown():
    hourly_df["date"] = hourly_df["timestamp"].dt.date
    daily = hourly_df.groupby("date")[[f"{a}_kwh" for a in APPLIANCES]].sum()
    daily.columns = [a.replace("_", " ").title() for a in APPLIANCES]
    
    fig, ax = plt.subplots(figsize=(14, 6))
    daily.plot(kind="bar", stacked=True, ax=ax, colormap="tab20", width=0.8)
    
    cutoff_date = PREDICTION_CUTOFF.date()
    if cutoff_date in daily.index:
        cutoff_idx = list(daily.index).index(cutoff_date)
        ax.axvline(x=cutoff_idx - 0.5, color="red", linestyle="--", linewidth=2, label="Prediction Split (Day 30)")
    
    ax.set_title("Daily Energy Consumption Breakdown by Appliance (History vs Prediction)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Energy Consumption (kWh)", fontsize=12)
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    
    plt.xticks(ticks=range(0, len(daily), 3), labels=[str(d)[5:] for d in daily.index[::3]], rotation=45)
    
    fig_path = FIG_DIR / "daily_energy_breakdown.png"
    plt.savefig(fig_path, dpi=300)
    plt.close()
    print(f"Saved: {fig_path}")

# =====================================================================================
# 2. Average Hourly Load Profile by Occupancy State
# =====================================================================================
def plot_hourly_profile():
    hourly_df["hour"] = hourly_df["timestamp"].dt.hour
    profile = hourly_df.groupby(["hour", "occupancy"])["total_kwh"].mean().reset_index()
    
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.lineplot(data=profile, x="hour", y="total_kwh", hue="occupancy", marker="o", linewidth=2.5, ax=ax)
    
    ax.set_title("Average Hourly Load Profile Across Occupancy States", fontsize=14, fontweight="bold")
    ax.set_xlabel("Hour of Day", fontsize=12)
    ax.set_ylabel("Average Hourly Energy (kWh)", fontsize=12)
    ax.set_xticks(range(0, 24))
    
    fig_path = FIG_DIR / "hourly_load_by_occupancy.png"
    plt.savefig(fig_path, dpi=300)
    plt.close()
    print(f"Saved: {fig_path}")

# =====================================================================================
# 3. Indoor vs Outdoor Temperature Dynamics (With Red Cutoff Line)
# =====================================================================================
def plot_temperature_dynamics():
    fig, ax1 = plt.subplots(figsize=(14, 5))
    
    ax1.plot(hourly_df["timestamp"], hourly_df["indoor_temp_c"], color="crimson", label="Indoor Temp (°C)", linewidth=1.5)
    ax1.plot(hourly_df["timestamp"], hourly_df["heating_setpoint_c"], color="darkorange", linestyle="--", label="Setpoint (°C)", linewidth=1.2)
    
    ax1.axvline(x=PREDICTION_CUTOFF, color="red", linestyle="--", linewidth=2, label="Prediction Split (Day 30)")
    
    ax1.set_xlabel("Date", fontsize=12)
    ax1.set_ylabel("Temperature (°C)", color="crimson", fontsize=12)
    ax1.tick_params(axis="y", labelcolor="crimson")
    
    ax2 = ax1.twinx()
    ax2.plot(hourly_df["timestamp"], hourly_df["temp_out_c"], color="dodgerblue", alpha=0.6, label="Outdoor Temp (°C)", linewidth=1)
    ax2.set_ylabel("Outdoor Temperature (°C)", color="dodgerblue", fontsize=12)
    ax2.tick_params(axis="y", labelcolor="dodgerblue")
    ax2.grid(False)
    
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper right", fontsize=9)
    
    plt.title("Apartment Thermal Dynamics: History vs Prediction Split", fontsize=14, fontweight="bold")
    
    fig_path = FIG_DIR / "temperature_dynamics.png"
    plt.savefig(fig_path, dpi=300)
    plt.close()
    print(f"Saved: {fig_path}")

# =====================================================================================
# 4. Average Daily Energy Consumption per Device: At Home vs Away
# =====================================================================================
def plot_home_vs_away_consumption():
    is_home = hourly_df["aleksandra_home_share"] > 0
    is_away = ~is_home
    
    # Calculate total equivalent days spent in each state
    home_days = is_home.sum() / 24.0
    away_days = is_away.sum() / 24.0
    
    # Average daily consumption per appliance for each state
    home_daily_avg = hourly_df[is_home][[f"{a}_kwh" for a in APPLIANCES]].sum() / home_days
    away_daily_avg = hourly_df[is_away][[f"{a}_kwh" for a in APPLIANCES]].sum() / away_days
    
    comp_df = pd.DataFrame({
        "Appliance": [a.replace("_", " ").title() for a in APPLIANCES],
        "At Home": home_daily_avg.values,
        "Away": away_daily_avg.values
    }).melt(id_vars="Appliance", var_name="Presence", value_name="Avg_kWh_Per_Day")
    
    order = comp_df[comp_df["Presence"] == "At Home"].sort_values(by="Avg_kWh_Per_Day", ascending=False)["Appliance"]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(
        data=comp_df, 
        x="Avg_kWh_Per_Day", 
        y="Appliance", 
        hue="Presence", 
        order=order, 
        palette=["#2ecc71", "#e74c3c"], 
        ax=ax
    )
    
    ax.set_title("Average Daily Energy Consumption per Device: Aleksandra At Home vs. Away", fontsize=14, fontweight="bold")
    ax.set_xlabel("Average Daily Energy Consumed (kWh / Day)", fontsize=12)
    ax.set_ylabel("Appliance", fontsize=12)
    
    for p in ax.patches:
        width = p.get_width()
        if width > 0:
            ax.annotate(f"{width:.2f}", (width, p.get_y() + p.get_height() / 2.),
                        ha="left", va="center", xytext=(4, 0), textcoords="offset points", fontsize=8)
    
    fig_path = FIG_DIR / "device_consumption_home_vs_away.png"
    plt.savefig(fig_path, dpi=300)
    plt.close()
    print(f"Saved: {fig_path}")

# =====================================================================================
# 5. Variance / Volatility of Hourly Consumption per Device (Percentage Share)
# =====================================================================================
def plot_device_variance():
    app_cols = [f"{a}_kwh" for a in APPLIANCES]
    
    variances = hourly_df[app_cols].var()
    total_var = variances.sum()
    
    var_pct = (variances / total_var * 100).reset_index()
    var_pct.columns = ["appliance_col", "variance_pct"]
    var_pct["Appliance"] = [a.replace("_", " ").title() for a in APPLIANCES]
    var_pct = var_pct.sort_values(by="variance_pct", ascending=False)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(data=var_pct, x="variance_pct", y="Appliance", palette="magma", ax=ax)
    
    ax.set_title("Device Hourly Consumption Variance (% of Total Household Variance)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Share of Total Variance (%)", fontsize=12)
    ax.set_ylabel("Appliance", fontsize=12)
    
    for p in ax.patches:
        width = p.get_width()
        ax.annotate(f"{width:.1f}%", (width, p.get_y() + p.get_height() / 2.),
                    ha="left", va="center", xytext=(5, 0), textcoords="offset points", fontsize=9, fontweight="bold")
    
    fig_path = FIG_DIR / "device_hourly_variance.png"
    plt.savefig(fig_path, dpi=300)
    plt.close()
    print(f"Saved: {fig_path}")

# =====================================================================================
# 6. Appliance Event Run Summary
# =====================================================================================
def plot_event_summary():
    event_summary = events_df.groupby("appliance").agg(
        count=("duration_min", "count"),
        avg_duration=("duration_min", "mean"),
        total_kwh=("kwh", "sum")
    ).reset_index()
    event_summary["Appliance"] = [a.replace("_", " ").title() for a in event_summary["appliance"]]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=event_summary, x="total_kwh", y="Appliance", palette="viridis", ax=ax)
    
    ax.set_title("Total Energy Consumption by Appliance Run Events", fontsize=14, fontweight="bold")
    ax.set_xlabel("Total Energy Consumed (kWh)", fontsize=12)
    ax.set_ylabel("Appliance", fontsize=12)
    
    fig_path = FIG_DIR / "appliance_events_summary.png"
    plt.savefig(fig_path, dpi=300)
    plt.close()
    print(f"Saved: {fig_path}")

if __name__ == "__main__":
    print("Generating complete visualization suite...")
    plot_daily_breakdown()
    plot_hourly_profile()
    plot_temperature_dynamics()
    plot_home_vs_away_consumption()
    plot_device_variance()
    plot_event_summary()
    print("All plots generated and exported successfully!")