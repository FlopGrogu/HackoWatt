/* Data service: the ONLY place screens get data from. Every method returns a Promise. The forecast JSON exported
   by src/export_app_data.py (data/app/forecast.json) drives the overview, peak-hours and usage charts; the
   static demo data (js/data/demo.js) fills in whatever the forecast does not cover (devices) and is the
   fallback when the file cannot be loaded. */
(() => {
  const copy = (value) => Promise.resolve(structuredClone(value));

  // The forecast is fetched once on load. Anything it does not contain (or all of it, when the file cannot be
  // loaded) comes from the static demo data.
  const forecast = fetch(HW.config.forecastUrl, { cache: 'no-cache' })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .catch((err) => {
      console.warn(`Forecast not loaded (${err.message}); using demo data`);
      return null;
    });
  const data = async () => ({ ...HW.demo, ...(await forecast) });

  HW.api = {
    /** Metadata of the loaded forecast ({ now, generated, llm, … }), null when the demo data is used. */
    getForecastMeta: async () => (await forecast)?.meta ?? null,
    getUser: async () => copy((await data()).user),
    getTariff: () => copy(HW.config.tariff),
    getOverview: async () => copy((await data()).overview),
    getPeakHours: async () => copy((await data()).peak),
    getUsage: async (range) => copy((await data()).usage[range]),
    /** Cheaper-time suggestions for predicted washer / dishwasher runs (see `shifts` in the forecast JSON). */
    getShifts: async () => copy((await data()).shifts ?? []),
    /** All devices (flat), each with the name of its room. */
    getDevices: () => copy(HW.demo.rooms.flatMap((room) => room.devices.map((d) => ({ ...d, room: room.name })))),

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
      const deviceCount = (await this.getDevices()).length;
      const humidityState = (h) => (h < 30 ? 'Dry' : h <= 60 ? 'Good' : 'Humid');
      return [
        { id: 'temperature', icon: 'thermometer', state: weather ? 'Outside' : '…',
          value: weather ? `${weather.temperature.toFixed(1)}°C` : '–', label: 'Temperature' },
        { id: 'humidity', icon: 'droplet', state: weather ? humidityState(weather.humidity) : '…',
          value: weather ? `${Math.round(weather.humidity)}%` : '–', label: 'Humidity' },
        { id: 'devices', icon: 'chip', state: 'Active', value: String(deviceCount), label: 'Devices',
          target: 'forecast' },
      ];
    },
  };
})();
