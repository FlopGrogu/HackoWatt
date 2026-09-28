/* Home dashboard: usage overview, time-of-use prices, peak demand hours, status tiles. */
document.addEventListener('alpine:init', () => {
  const BOX = { width: 300, height: 110, pad: 14 };
  const DAY_MINUTES = 24 * 60;
  const hh = (h) => String(h % 24).padStart(2, '0');

  Alpine.data('homeScreen', () => ({
    user: {}, tariff: [], overview: null, peak: null, tiles: [],

    async init() {
      [this.user, this.tariff, this.overview, this.peak, this.tiles] = await Promise.all([
        HW.api.getUser(), HW.api.getTariff(), HW.api.getOverview(),
        HW.api.getPeakHours(), HW.api.getHomeTiles(null),
      ]);
      this.$watch(() => JSON.stringify(Alpine.store('profile').location), () => this.refreshWeather());
      this.refreshWeather();
    },

    // --- live weather at the stored location ---
    async refreshWeather() {
      const { lat, lon } = Alpine.store('profile').location;
      let weather = null;
      try {
        weather = await HW.api.getWeather({ lat, lon });
      } catch (err) {
        console.warn('Weather unavailable', err);
      }
      this.tiles = await HW.api.getHomeTiles(weather);
    },

    // --- usage overview chart ---
    get overviewChart() {
      if (!this.overview) return { actual: '', forecast: '', nowStyle: '' };
      const c = HW.charts.actualAndForecast(this.overview.actual, this.overview.forecast, BOX);
      return { ...c, nowStyle: HW.charts.position(c.last, BOX.width, BOX.height) };
    },

    // --- tariff bar ---
    // The day axis runs 00:00 → 23:59 (1440 minutes); the fake clock drives every "now" indicator.
    get minutes() {
      return Alpine.store('clock').minutes;
    },
    isNow(seg) {
      return this.minutes >= seg.from * 60 && this.minutes < seg.to * 60;
    },
    tariffLabel(seg) {
      const span = seg.to - seg.from;
      if (span <= 2) return `${hh(seg.from)}–${hh(seg.to)}`;           // too narrow for full times
      if (span <= 5) return `${hh(seg.from)}–${hh(seg.to)}h`;
      return `${hh(seg.from)}:00–${hh(seg.to)}:00`;
    },
    get nowStyle() {
      return `left:${(this.minutes / DAY_MINUTES) * 100}%`;
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
