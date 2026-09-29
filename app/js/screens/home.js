/* Home dashboard: usage overview, time-of-use prices, peak demand hours, status tiles. */
document.addEventListener('alpine:init', () => {
  const DAY_MINUTES = 24 * 60;
  const hh = (h) => String(h % 24).padStart(2, '0');

  Alpine.data('homeScreen', () => ({
    user: {}, presence: null, week: [], tariff: [], overview: null, peak: null, tiles: [], fade: { left: false, right: true },

    async init() {
      [this.user, this.tariff, this.overview, this.peak, this.tiles] = await Promise.all([
        HW.api.getUser(), HW.api.getTariff(), HW.api.getOverview(),
        HW.api.getPeakHours(), HW.api.getHomeTiles(null),
      ]);
      [this.presence, this.week] = await Promise.all([HW.api.getPresence(), HW.api.getWeekPlan()]);
      this.$watch(() => JSON.stringify(Alpine.store('profile').location), () => this.refreshWeather());
      this.refreshWeather();
    },

    // --- greeting follows the distance between the phone and home ---
    get greeting() {
      const km = this.presence?.km ?? 0;
      if (!this.presence || this.presence.home) return 'Welcome home,';
      return km < 5 ? 'Hello,' : km < 50 ? 'Enjoy your day,' : 'Safe travels,';
    },
    get statusLine() {
      if (!this.presence || this.presence.home) return this.user.status;
      const km = this.presence.km;
      return `${km < 1 ? `${Math.round(km * 1000)} m` : km < 10 ? `${km.toFixed(1)} km` : `${Math.round(km)} km`} from home`;
    },
    get away() {
      return !!this.presence && !this.presence.home;
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
        weather = await HW.api.getWeather({ ...Alpine.store('profile').location, lat, lon });
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
    // --- peak demand: legend + axis derived from the data (hours from … to inclusive) ---
    get peakLabel() {
      return this.peak && `${hh(this.peak.from)}–${hh(this.peak.to + 1)}`;
    },
    /** 00:00 / 06:00 / 12:00 / 18:00 ticks (dropped where they would collide with the peak label) + 24:00 end. */
    get peakAxis() {
      if (!this.peak) return [];
      const { from, to } = this.peak;
      const center = (from + to + 1) / 2;
      const ticks = [0, 6, 12, 18].filter((h) => h === 0 || Math.abs(h - center) > 4)
        .map((h) => ({ text: `${hh(h)}:00`, at: (h / 24) * 100, cls: h === 0 ? 'first' : '' }));
      return [...ticks, { text: this.peakLabel, at: (center / 24) * 100, cls: 'accent' },
        { text: '23:00', at: 100, cls: 'last' }];
    },

    get nowStyle() {
      return `left:${(this.minutes / DAY_MINUTES) * 100}%`;
    },
  }));
});
