/* Home dashboard: usage overview, time-of-use prices, peak demand hours, status tiles. */
document.addEventListener('alpine:init', () => {
  const DAY_MINUTES = 24 * 60;
  const hh = (h) => String(h % 24).padStart(2, '0');

  Alpine.data('homeScreen', () => ({
    user: {}, tariff: [], overview: null, peak: null, tiles: [], fade: { left: false, right: true },

    async init() {
      [this.user, this.tariff, this.overview, this.peak, this.tiles] = await Promise.all([
        HW.api.getUser(), HW.api.getTariff(), HW.api.getOverview(),
        HW.api.getPeakHours(), HW.api.getHomeTiles(null),
      ]);
      this.$watch(() => JSON.stringify(Alpine.store('profile').location), () => this.refreshWeather());
      this.refreshWeather();
    },

    // --- status tiles: fade the edge(s) that have more content to scroll to ---
    onTilesScroll(el) {
      this.fade = { left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 };
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

    // --- charts (Chart.js specs, see js/charts.js) ---
    get overviewSpec() {
      return this.overview && HW.charts.overview(this.overview);
    },
    get peakSpec() {
      return this.peak && HW.charts.hourly(this.peak);
    },

    // --- tariff bar ---
    // The day axis runs 00:00 → 23:59 (1440 minutes); the fake clock drives every "now" indicator.
    get minutes() {
      return Alpine.store('clock').minutes;
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
  }));
});
