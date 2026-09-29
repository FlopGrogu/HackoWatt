/* Profile / Settings: account header, fake clock, location (with Leaflet map preview) and data management. */
document.addEventListener('alpine:init', () => {
  L.Icon.Default.imagePath = 'vendor/leaflet/images/';   // vendored marker images

  Alpine.data('settingsScreen', () => ({
    editingTime: false, editingLocation: false,
    draft: '',                                   // the date being typed; only applied with "Set this date"
    seasons: [
      { name: 'Winter', short: 'Jan', month: 0, active: (d) => [11, 0, 1].includes(d.getMonth()) },
      { name: 'Spring', short: 'Apr', month: 3, active: (d) => [2, 3, 4].includes(d.getMonth()) },
      { name: 'Summer', short: 'Jul', month: 6, active: (d) => [5, 6, 7].includes(d.getMonth()) },
      { name: 'Autumn', short: 'Oct', month: 9, active: (d) => [8, 9, 10].includes(d.getMonth()) },
    ],
    query: '', places: [], searchError: '',
    map: null, marker: null,

    init() {
      this.draft = Alpine.store('clock').iso;
      this.$watch(() => Alpine.store('profile').location, () => this.showLocation());
      this.$watch('editingLocation', (open) => open && this.$nextTick(() => this.showLocation()));
    },

    get clock() {
      return Alpine.store('clock');
    },

    // --- current date: nothing changes until it is confirmed ---
    get canApply() {
      return /^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(this.draft) && this.draft !== this.clock.iso;
    },
    applyDraft() {
      if (this.canApply) this.clock.set(this.draft);
    },
    /** Jump to the 15th of the season's month (same year and time of day). */
    pickSeason(season) {
      const d = this.clock.date;
      const pad = (n) => String(n).padStart(2, '0');
      this.clock.set(`${d.getFullYear()}-${pad(season.month + 1)}-15T${pad(d.getHours())}:${pad(d.getMinutes())}`);
    },

    // --- location search ---
    async search() {
      const q = this.query.trim();
      this.searchError = '';
      if (q.length < 2) { this.places = []; return; }
      try {
        this.places = await HW.api.searchPlaces(q);
        if (!this.places.length) this.searchError = 'No places found';
      } catch {
        this.places = [];
        this.searchError = 'Search unavailable (offline?)';
      }
    },
    pick(place) {
      Alpine.store('profile').setLocation(place);
      this.query = '';
      this.places = [];
    },

    // --- map preview (created lazily: Leaflet needs a visible container) ---
    showLocation() {
      if (!this.editingLocation) return;
      const { lat, lon } = Alpine.store('profile').location;
      if (!this.map) {
        this.map = L.map(this.$refs.map).setView([lat, lon], 10);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 18, attribution: '&copy; OpenStreetMap',
        }).addTo(this.map);
        this.marker = L.marker([lat, lon]).addTo(this.map);
      }
      this.map.invalidateSize();
      this.map.setView([lat, lon], this.map.getZoom());
      this.marker.setLatLng([lat, lon]);
    },
  }));
});
