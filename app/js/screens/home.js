/* Home dashboard: usage overview, time-of-use prices, peak demand hours, status tiles. */
document.addEventListener('alpine:init', () => {
  const BOX = { width: 300, height: 110, pad: 14 };
  const hh = (h) => String(h % 24).padStart(2, '0');

  Alpine.data('homeScreen', () => ({
    user: {}, now: { hour: 0 }, tariff: [], overview: null, peak: null, tiles: [],

    async init() {
      [this.user, this.now, this.tariff, this.overview, this.peak, this.tiles] = await Promise.all([
        HW.api.getUser(), HW.api.getNow(), HW.api.getTariff(), HW.api.getOverview(),
        HW.api.getPeakHours(), HW.api.getHomeTiles(),
      ]);
    },

    // --- usage overview chart ---
    get overviewChart() {
      if (!this.overview) return { actual: '', forecast: '', nowStyle: '' };
      const c = HW.charts.actualAndForecast(this.overview.actual, this.overview.forecast, BOX);
      return { ...c, nowStyle: HW.charts.position(c.last, BOX.width, BOX.height) };
    },

    // --- tariff bar ---
    isNow(seg) {
      return this.now.hour >= seg.from && this.now.hour < seg.to;
    },
    tariffLabel(seg) {
      const span = seg.to - seg.from;
      if (span <= 2) return `${hh(seg.from)}–${hh(seg.to)}`;           // too narrow for full times
      if (span <= 5) return `${hh(seg.from)}–${hh(seg.to)}h`;
      return `${hh(seg.from)}:00–${hh(seg.to)}:00`;
    },
    get nowStyle() {
      return `left:${(this.now.hour / 24) * 100}%`;
    },

    // --- peak demand bars ---
    isPeak(hour) {
      return this.peak && hour >= this.peak.from && hour <= this.peak.to;
    },
    barStyle(value) {
      const max = Math.max(...(this.peak?.hours || [1]));
      return `height:${(value / max) * 100}%`;
    },
  }));
});
