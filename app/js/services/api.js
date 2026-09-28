/* Data service: the ONLY place screens get data from. Every method returns a Promise, so switching from
   the static demo data to the real forecast (e.g. fetch('/api/forecast?hours=24') or a JSON file exported
   by src/run_forecast.py) only changes this file – the screens stay as they are. */
(() => {
  const copy = (value) => Promise.resolve(structuredClone(value));
  const demo = () => HW.demo;

  HW.api = {
    getUser: () => copy(demo().user),
    getTariff: () => copy(HW.config.tariff),
    getOverview: () => copy(demo().overview),
    getPeakHours: () => copy(demo().peak),
    getUsage: (range) => copy(demo().usage[range]),
    getRooms: () => copy(demo().rooms),

    /** Live conditions at a location from Open-Meteo (https://open-meteo.com/en/docs). */
    async getWeather({ lat, lon }) {
      const url = 'https://api.open-meteo.com/v1/forecast?current=temperature_2m,relative_humidity_2m' +
                  `&latitude=${lat}&longitude=${lon}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Open-Meteo: HTTP ${res.status}`);
      const { current } = await res.json();
      return { temperature: current.temperature_2m, humidity: current.relative_humidity_2m };
    },

    /** Place search for the location setting (Open-Meteo geocoding). */
    async searchPlaces(query) {
      const url = `https://geocoding-api.open-meteo.com/v1/search?count=5&language=en&name=${encodeURIComponent(query)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Open-Meteo geocoding: HTTP ${res.status}`);
      const { results = [] } = await res.json();
      return results.map((r) => ({
        name: [r.name, r.admin1 && r.admin1 !== r.name ? r.admin1 : null, r.country].filter(Boolean).join(', '),
        lat: r.latitude, lon: r.longitude,
      }));
    },

    /** Home status tiles; `weather` is null while loading or when the request failed. */
    async getHomeTiles(weather) {
      const rooms = await this.getRooms();
      const deviceCount = rooms.reduce((n, room) => n + room.devices.length, 0);
      const humidityState = (h) => (h < 30 ? 'Dry' : h <= 60 ? 'Good' : 'Humid');
      return [
        { id: 'temperature', icon: 'thermometer', state: weather ? 'Outside' : '…',
          value: weather ? `${weather.temperature.toFixed(1)}°C` : '–', label: 'Temperature', highlight: true },
        { id: 'humidity', icon: 'droplet', state: weather ? humidityState(weather.humidity) : '…',
          value: weather ? `${Math.round(weather.humidity)}%` : '–', label: 'Humidity' },
        { id: 'devices', icon: 'chip', state: 'Active', value: String(deviceCount), label: 'Devices',
          target: 'devices' },
      ];
    },
  };
})();
