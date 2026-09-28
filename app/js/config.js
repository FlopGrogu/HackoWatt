/* Global namespace + app-wide constants. Loaded first; every other file adds to window.HW. */
window.HW = window.HW || {};

HW.config = {
  currency: '€',
  // Forecast written by src/export_app_data.py. Relative to index.html: serve the repository root (e.g.
  // `python -m http.server` there, then open /app/). If it cannot be loaded the app falls back to js/data/demo.js.
  forecastUrl: '../data/app/forecast.json',
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
