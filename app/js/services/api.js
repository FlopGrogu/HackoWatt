/* Data service: the ONLY place screens get data from. Every method returns a Promise. The forecast JSON exported
   by src/export_app_data.py (data/app/forecast.json) drives the overview, peak-hours and usage charts; the
   static demo data (js/data/demo.js) fills in whatever the forecast does not cover (devices) and is the
   fallback when the file cannot be loaded. */
(() => {
  const copy = (value) => Promise.resolve(structuredClone(value));

  // "Now" is the fake clock at page load (changing it in the settings reloads the app). Its date, in any year, is wrapped
  // onto the generated year 2026; only the 30 days before it are used (js/services/dataset.js).
  const now = HW.nowAtLoad();
  const yearShift = now.getFullYear() - HW.dataset.YEAR;          // 2026 → the year the user picked
  const shiftIso = (iso) => (iso ? iso.replace(/^\d{4}/, (y) => String(Number(y) + yearShift)) : iso);
  const SLOTS = [18, 12, 6, 0];                                    // forecasts exist for these hours of every day
  const view = HW.dataset.at(now);

  const json = (url) => fetch(url, { cache: 'no-cache' }).then((res) => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  });

  // Forecast for the latest slot at or before now (data/app/forecast/<day>.json, from src/export_app_data.py --all), with all
  // its timestamps moved into the picked year. Falls back to the single exported forecast, then to the demo data.
  const forecast = json(HW.config.forecastDayUrl.replace('{date}', HW.dataset.canonicalDay(now)))
    .then(({ slots }) => {
      const slot = SLOTS.find((h) => h <= now.getHours());
      const data = slots[String(slot).padStart(2, '0')];
      data.meta.now = shiftIso(data.meta.now);
      for (const s of data.shifts ?? []) { s.usual = shiftIso(s.usual); s.ideal = shiftIso(s.ideal); }
      return data;
    })
    .catch((err) => {
      console.warn(`Day forecast not loaded (${err.message}); trying ${HW.config.forecastUrl}`);
      return json(HW.config.forecastUrl);
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
    /** Home card: metered days come from the consumption file, the forecast days from the forecast file. */
    async getOverview() {
      const overview = structuredClone((await data()).overview);
      const days = (await view).dailyTotals(28);
      if (days) {
        const future = overview.pointLabels.slice(overview.actual.length);
        overview.actual = days.map((d) => Math.round(d.kwh * 10) / 10);
        overview.pointLabels = [...days.map((d) => d.label), ...future];
        overview.labels = [days[0].label, days[14].label, ...overview.labels.slice(2)];
      }
      return overview;
    },
    async getPeakHours() {
      return copy((await (await view).peakHours()) ?? (await data()).peak);
    },
    getUsage: async (range) => copy((await data()).usage[range]),
    /** Cheaper-time suggestions for predicted washer / dishwasher runs (see `shifts` in the forecast JSON). */
    getShifts: async () => copy((await data()).shifts ?? []),
    /** All devices (flat), each with the name of its room. */
    getDevices: () => copy(HW.demo.rooms.flatMap((room) => room.devices.map((d) => ({ ...d, room: room.name })))),

    /** Outdoor conditions in the current hour, from the generated weather data (null if it could not be read). */
    getWeather: async () => (await view).weather(),

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

    /** Home status tiles; `weather` is null while loading or when the data is missing. */
    async getHomeTiles(weather) {
      const [deviceCount, ds] = [(await this.getDevices()).length, await view];
      const humidityState = (h) => (h < 30 ? 'Dry' : h <= 60 ? 'Good' : 'Humid');
      const presence = ds.presence();
      const agenda = ds.agenda();
      const tiles = [
        { id: 'temperature', icon: 'thermometer', state: weather ? 'Outside' : '…',
          value: weather ? `${weather.temperature.toFixed(1)}°C` : '–', label: 'Temperature' },
        { id: 'humidity', icon: 'droplet', state: weather ? humidityState(weather.humidity) : '…',
          value: weather ? `${Math.round(weather.humidity)}%` : '–', label: 'Humidity' },
      ];
      if (presence) {
        tiles.push({ id: 'presence', icon: 'pin', state: 'Phone', value: presence.home ? 'Home' : `${presence.km < 10 ? presence.km.toFixed(1) : Math.round(presence.km)} km`, label: presence.home ? 'You are at home' : 'Away from home' });
      }
      if (agenda) {
        tiles.push({ id: 'today', icon: 'clock', state: 'Calendar', value: agenda.today.split(' – ')[0], label: agenda.today.includes(' – ') ? agenda.today.split(' – ')[1] : 'Today' });
        if (agenda.next) tiles.push({ id: 'trip', icon: 'clock', state: `in ${agenda.next.in} d`, value: agenda.next.place, label: 'Next trip' });
      }
      tiles.push({ id: 'devices', icon: 'chip', state: 'Active', value: String(deviceCount), label: 'Devices', target: 'forecast' });
      return tiles;
    },
  };
})();
