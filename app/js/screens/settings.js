/* Profile / Settings: account header, fake clock, location (with Leaflet map preview) and data management. */
document.addEventListener('alpine:init', () => {
  L.Icon.Default.imagePath = 'vendor/leaflet/images/';   // vendored marker images

  Alpine.data('settingsScreen', () => ({
    editingTime: false, editingLocation: false,
    query: '', places: [], searchError: '',
    map: null, marker: null,

    init() {
      this.$watch(() => Alpine.store('profile').location, () => this.showLocation());
      this.$watch('editingLocation', (open) => open && this.$nextTick(() => this.showLocation()));
    },

    get clock() {
      return Alpine.store('clock');
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
