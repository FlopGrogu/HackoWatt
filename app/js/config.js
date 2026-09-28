/* Global namespace + app-wide constants. Loaded first; every other file adds to window.HW. */
window.HW = window.HW || {};

HW.config = {
  currency: '€',
  // Official HackoWatt time-of-use tariff (common challenge assumptions)
  tariff: [
    { from: 0, to: 6, price: 0.18, tone: 'low' },
    { from: 6, to: 17, price: 0.28, tone: 'mid' },
    { from: 17, to: 22, price: 0.40, tone: 'high' },
    { from: 22, to: 24, price: 0.28, tone: 'mid' },
  ],
  // How each appliance is forecast (same four types as the Python forecast blocks)
  models: {
    fixed: 'Fixed model',
    unshiftable: 'Unshiftable model',
    shiftable: 'Shiftable model',
    physical: 'Physical model',
  },
  ranges: ['24h', '3d', '7d'],
  tabs: [
    { id: 'home', label: 'Home' },
    { id: 'search', label: 'Search' },
    { id: 'devices', label: 'Devices' },
    { id: 'profile', label: 'Profile' },
  ],
};
