/* Static demo data (no logic). Values are taken from / shaped like the simulated household
   (1 Sep – 12 Oct 2026). Replace by real forecast output through js/services/api.js, not here. */
HW.demo = {
  user: { status: 'All systems running normally' },

  // kWh per day, averaged over 4 days: 7 metered points (1–28 Sep) + 2 forecast points (29 Sep – 5 Oct)
  overview: {
    actual: [4.6, 6.4, 5.1, 3.5, 5.4, 7.2, 5.4],
    forecast: [4.7, 5.6],
    labels: ['1 Sep', '14 Sep', '28 Sep'],
  },

  // Average kWh per hour of day (home "Peak Demand Hours" card)
  peak: {
    hours: [0.10, 0.09, 0.09, 0.09, 0.09, 0.13, 0.25, 0.33, 0.19, 0.16, 0.15, 0.13,
            0.20, 0.14, 0.13, 0.14, 0.13, 0.15, 0.22, 0.33, 0.25, 0.24, 0.20, 0.12],
    from: 18, to: 21,
    text: 'Your highest energy demand is typically between 18–22 h on weekdays.',
  },

  // Energy Usage screen, one entry per time range
  usage: {
    '24h': {
      title: 'Forecast Profile', subtitle: 'Hour-level granularity (next 24 h)',
      labels: ['18:00', '00:00', '06:00', '12:00', '17:00'],
      values: [0.62, 0.48, 0.41, 0.35, 0.30, 0.12, 0.10, 0.09, 0.09, 0.10, 0.14, 0.26, 1.53, 0.36, 0.23,
               0.15, 0.13, 0.12, 0.18, 0.14, 0.12, 0.13, 0.15, 0.24],
      highlights: [
        { index: 0, title: 'Evening peak', detail: '18:00 • 0.62 kWh' },
        { index: 12, title: 'Hot-water reheat', detail: '06:00 • 1.53 kWh' },
      ],
      incidents: [
        { title: 'Heat pump', value: '+1.4 kW', time: '06:10', tone: 'accent' },
        { title: 'Dishwasher', value: '+2.0 kW', time: '21:30', tone: 'accent' },
        { title: 'Away', value: '−0.3 kW', time: '08:15', tone: 'green' },
      ],
      summaryTitle: 'Daily Summary',
      summary: [
        { label: 'Total', value: '4.6 kWh', delta: '8% vs yesterday', good: true },
        { label: 'Peak usage', value: '1.5 kW', delta: '5% vs normal', good: false },
        { label: 'Total cost', value: '€1.35', delta: '€0.21 saved', good: true, accent: true },
      ],
    },
    '3d': {
      title: 'Forecast Profile', subtitle: '4-hour granularity (next 3 days)',
      labels: ['Tue', 'Wed', 'Thu'],
      values: [0.9, 1.6, 0.6, 0.5, 1.1, 0.8, 0.8, 1.4, 0.5, 0.4, 1.2, 0.9, 0.7, 1.7, 0.6, 0.5, 1.3, 1.0],
      highlights: [
        { index: 7, title: 'Morning warm-up', detail: 'Wed 06:00 • 1.4 kWh' },
        { index: 13, title: 'Hot-water reheat', detail: 'Thu 06:00 • 1.7 kWh' },
      ],
      incidents: [
        { title: 'Heat pump', value: '+2.1 kW', time: 'Wed 06:05', tone: 'accent' },
        { title: 'Washing', value: '+2.0 kW', time: 'Tue 19:00', tone: 'accent' },
        { title: 'Away', value: '−0.4 kW', time: 'Thu 08:20', tone: 'green' },
      ],
      summaryTitle: '3-Day Summary',
      summary: [
        { label: 'Avg daily', value: '4.8 kWh', delta: '3% vs last 3 days', good: true },
        { label: 'Peak usage', value: '2.1 kW', delta: '9% vs normal', good: false },
        { label: 'Total cost', value: '€4.10', delta: '€0.55 saved', good: true, accent: true },
      ],
    },
    '7d': {
      title: 'Historical Profile', subtitle: 'Hour-level granularity (30d scope)',
      labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      values: [3.1, 3.6, 5.3, 3.4, 4.5, 4.1, 3.2, 5.9, 2.8],
      highlights: [
        { index: 2, title: 'Guest evening', detail: 'Wed 19:00 • 5.3 kWh' },
        { index: 4, title: 'Laundry after trip', detail: 'Thu 08:00 • 4.5 kWh' },
        { index: 7, title: 'Pierogi night', detail: 'Sat 19:00 • 5.9 kWh' },
        { index: 8, title: 'Away weekend', detail: 'Sun • 2.8 kWh' },
      ],
      incidents: [
        { title: 'Away (Berlin)', value: '−1.8 kW', time: 'Tue 05:30', tone: 'green' },
        { title: 'Guests', value: '+2.5 kW', time: 'Sat 19:10', tone: 'accent' },
        { title: 'HP Surge', value: '+2.4 kW', time: 'Fri 06:05', tone: 'accent' },
      ],
      summaryTitle: 'Weekly Summary',
      summary: [
        { label: 'Avg daily', value: '5.4 kWh', delta: '4% vs last week', good: true },
        { label: 'Peak usage', value: '2.6 kW', delta: '12% vs normal', good: false },
        { label: 'Total cost', value: '€11.20', delta: '€1.40 saved', good: true, accent: true },
      ],
    },
  },

  // Devices screen: rooms → devices (model = how the forecast treats the device)
  rooms: [
    { name: 'Kitchen', devices: [
      { name: 'Refrigerator', icon: 'fridge', model: 'fixed', watts: 150 },
      { name: 'Kettle', icon: 'kettle', model: 'unshiftable', watts: 2000 },
      { name: 'Coffee machine', icon: 'coffee', model: 'unshiftable', watts: 1200 },
      { name: 'Oven', icon: 'oven', model: 'unshiftable', watts: 2500 },
      { name: 'Dishwasher', icon: 'dishwasher', model: 'shiftable', watts: 1800 },
    ] },
    { name: 'Living Room', devices: [
      { name: 'Television', icon: 'tv', model: 'unshiftable', watts: 120 },
      { name: 'Wi-Fi router', icon: 'wifi', model: 'fixed', watts: 12 },
      { name: 'Lighting', icon: 'bulb', model: 'unshiftable', watts: 60 },
      { name: 'Phone / tablet charging', icon: 'charging', model: 'unshiftable', watts: 15 },
    ] },
    { name: 'Laundry', devices: [
      { name: 'Washing machine', icon: 'washer', model: 'shiftable', watts: 500 },
      { name: 'Electric heating / heat pump', icon: 'heatpump', model: 'physical', watts: 3000 },
    ] },
    { name: 'Office', devices: [
      { name: 'Laptop', icon: 'laptop', model: 'unshiftable', watts: 65 },
    ] },
  ],
};
