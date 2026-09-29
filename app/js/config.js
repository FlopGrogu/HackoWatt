/* Global namespace + app-wide constants. Loaded first; every other file adds to window.HW. */
window.HW = window.HW || {};

HW.config = {
  // Forecast written by src/export_app_data.py. Relative to index.html: serve the repository root (e.g.
  // `python -m http.server` there, then open /app/). If it cannot be loaded the app falls back to js/data/demo.js.
  forecastUrl: '../data/app/forecast.json',
  // One file per day with the forecasts for 00/06/12/18 h (src/export_app_data.py --all); {date} = YYYY-MM-DD of 2026.
  forecastDayUrl: '../data/app/forecast/{date}.json',
  // PV simulator results (src/simulate_pv.py): 0–6 kWp, scenarios A (as today) and B (with shifting).
  pvUrl: '../data/app/pv_simulation.json',
  // The generated year (src/generate_all.py): the app reads all of it but only ever looks at the last 30 days.
  dataUrls: {
    consumption: '../data/consumption/hourly_consumption.csv',
    weather: '../data/weather/weather_hourly.csv',
    sun: '../data/weather/sun_times.csv',
    positions: '../data/geolocation/positions.csv',
    calendar: '../data/calendar/aleksandra_calendar_2026.ics',
  },
  // Location the generated data belongs to (Warsaw) and the real weather year that is replayed as 2026.
  dataLocation: { lat: 52.2297, lon: 21.0122 },
  weatherYear: 2025,
  home: { lat: 52.2296, lon: 21.0030 },               // ul. Chmielna 71 (phone within 150 m = at home)
  // Official HackoWatt time-of-use tariff (common challenge assumptions)
  tariff: [
    { from: 0, to: 6, price: 0.18, tone: 'low' },
    { from: 6, to: 17, price: 0.28, tone: 'mid' },
    { from: 17, to: 22, price: 0.40, tone: 'high' },
    { from: 22, to: 24, price: 0.28, tone: 'mid' },
  ],
  // How each appliance is forecast (same four types as the Python forecast blocks), in display order:
  // flexible loads first, then the ones that cannot move; always-on and heating last.
  deviceGroups: [
    { model: 'shiftable', title: 'Shiftable', hint: 'Can be moved to cheaper hours' },
    { model: 'unshiftable', title: 'Fixed-time', hint: 'Runs when you use it' },
    { model: 'fixed', title: 'Always-on', hint: 'Runs around the clock' },
    { model: 'physical', title: 'Heating', hint: 'Follows the weather and your comfort settings' },
  ],
  ranges: ['24h', '3d', '7d'],
  tabs: [
    { id: 'home', label: 'Home' },
    { id: 'forecast', label: 'Forecast' },
    { id: 'profile', label: 'Profile' },
  ],
};

/** The fake "current time" at page load: system clock + the offset saved by the Current Time setting. */
HW.nowAtLoad = () => {
  try {
    const saved = Number(localStorage.getItem('hw.clockOffset'));
    if (Number.isFinite(saved)) return new Date(Date.now() + saved);
  } catch { /* storage unavailable */ }
  return new Date();
};

HW.fmt = {
  /** Amounts under one euro are shown in cents ("28¢"), larger ones in euros ("€1.40"). */
  money: (euros) => (Math.abs(euros) < 1 ? `${Math.round(euros * 100)}¢` : `€${euros.toFixed(2)}`),
};
