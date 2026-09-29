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

    /** Where the phone is now: { home, km } (null if the positions could not be read). */
    getPresence: async () => (await view).presence(),

    /** The next 7 days starting today: expected presence from the calendar. */
    async getWeekPlan() {
      const ds = await view;
      return Array.from({ length: 7 }, (_, i) => {
        const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
        return { date: d.getTime(), weekday: d.toLocaleString('en-US', { weekday: 'short' }), day: d.getDate(), today: i === 0, ...ds.plan(d) };
      }).filter((d) => d.state);
    },

    /** All calendar entries of one day (a Date or ms), all-day first. */
    async getDayEvents(date) {
      return (await view).events(new Date(date));
    },

    /** One month of the calendar view (Monday first): [{ day, inMonth, state, label, note, today }] in 6 rows of 7. */
    async getMonthPlan(year, month) {
      const ds = await view;
      const first = new Date(year, month, 1);
      const offset = (first.getDay() + 6) % 7;
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      return Array.from({ length: 42 }, (_, i) => {
        const d = new Date(year, month, 1 - offset + i);
        return { date: d.getTime(), day: d.getDate(), inMonth: d.getMonth() === month, today: d.getTime() === today, ...ds.plan(d) };
      });
    },

    /** Outdoor conditions in the current hour at a location: { temperature, humidity, sunrise, sunset, place }.
        At the location the data was generated for (Warsaw) they come from the generated files; anywhere else the same date of
        the replayed weather year is fetched from Open-Meteo for that place (falls back to the generated data when offline). */
    async getWeather(location = Alpine.store('profile').location) {
      const ds = await view;
      const local = ds.weather() && ds.sun() ? { ...ds.weather(), ...ds.sun(), place: location.name, source: 'data' } : ds.weather();
      const km = Math.hypot((location.lat - HW.config.dataLocation.lat) * 111.32,
                            (location.lon - HW.config.dataLocation.lon) * 111.32 * Math.cos((location.lat * Math.PI) / 180));
      if (km < 30) return local;
      const day = HW.dataset.canonicalDay(now).replace(/^\d{4}/, HW.config.weatherYear);
      try {
        const url = 'https://archive-api.open-meteo.com/v1/archive?hourly=temperature_2m,relative_humidity_2m&daily=sunrise,sunset&timezone=auto' +
                    `&latitude=${location.lat}&longitude=${location.lon}&start_date=${day}&end_date=${day}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const { hourly, daily } = await res.json();
        const h = now.getHours();
        return { temperature: hourly.temperature_2m[h], humidity: hourly.relative_humidity_2m[h], place: location.name, source: 'open-meteo',
                 sunrise: daily.sunrise[0].slice(11, 16), sunset: daily.sunset[0].slice(11, 16) };
      } catch (err) {
        console.warn(`Weather for ${location.name} unavailable (${err.message}); using the generated data`);
        return local;
      }
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

    /** Home status tiles; `weather` is null while loading or when the data is missing. */
    async getHomeTiles(weather) {
      const [deviceCount, ds] = [(await this.getDevices()).length, await view];
      const humidityState = (h) => (h < 30 ? 'Dry' : h <= 60 ? 'Good' : 'Humid');
      const city = (weather?.place ?? Alpine.store('profile').location.name).split(',')[0];
      const tiles = [
        { id: 'temperature', icon: 'thermometer', state: weather ? city : '…',
          value: weather ? `${weather.temperature.toFixed(1)}°C` : '–', label: 'Temperature' },
        { id: 'humidity', icon: 'droplet', state: weather ? humidityState(weather.humidity) : '…',
          value: weather ? `${Math.round(weather.humidity)}%` : '–', label: 'Humidity' },
      ];
      if (weather?.sunrise && weather?.sunset) {
        const mins = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3));
        const len = mins(weather.sunset) - mins(weather.sunrise);
        tiles.push({ id: 'daylight', icon: 'bulb', state: `↑ ${weather.sunrise}`, value: `${Math.floor(len / 60)}h ${String(len % 60).padStart(2, '0')}m`, label: `Daylight · ↓ ${weather.sunset}` });
      }
      tiles.push({ id: 'devices', icon: 'chip', state: 'Active', value: String(deviceCount), label: 'Devices', target: 'forecast' });
      return tiles;
    },
  };
})();
