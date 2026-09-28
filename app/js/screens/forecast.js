/* Forecast tab: 24h / 3d / 7d profile with highlighted points (devices list: see devices.js). */
document.addEventListener('alpine:init', () => {
  Alpine.data('forecastScreen', () => ({
    ranges: HW.config.ranges,
    range: '7d',
    data: null,
    meta: null,          // metadata of the loaded forecast (null = demo data)

    async init() {
      this.meta = await HW.api.getForecastMeta();
      await this.load();
    },

    /** "Forecast for 28 Sep 17:00" – the moment the exported forecast starts. */
    get forecastNote() {
      if (!this.meta) return 'Showing demo data (forecast file not loaded)';
      const start = new Date(this.meta.now).toLocaleString('en-US', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
      return `Forecast from ${start}`;
    },

    async setRange(range) {
      this.range = range;
      await this.load();
    },

    async load() {
      this.data = await HW.api.getUsage(this.range);
    },

    get profileSpec() {
      const shifts = Alpine.store('shifts');
      return this.data && HW.charts.profile(this.data, {
        start: this.meta?.now && new Date(this.meta.now),      // time of point 0 …
        stepHours: this.data.stepHours,                        // … and the spacing between points
        shifts: { pending: shifts.pending, confirmed: shifts.confirmed },
        onPick: (shift) => shifts.select(shift),
      });
    },
    get pendingCount() {
      return Alpine.store('shifts').pending.length;
    },
  }));
});
