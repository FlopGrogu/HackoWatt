/* The generated year of data (2026), read straight from the repository's data/ folder:
     consumption (hourly kWh per appliance), weather (observed), phone positions (every 15 min) and the calendar (.ics).
   The app only ever looks at the 30 days before the (fake) current time. A date in any year is wrapped onto the same
   month/day of 2026 (29 Feb → 28 Feb), and the year is circular: 30 days before 10 Jan are 11 Dec – 10 Jan.
   Everything returned here is labelled with the dates of the year the user picked, not with 2026. */
(() => {
  const YEAR = 2026;
  const WINDOW_DAYS = 30;
  const HOURS = 365 * 24;
  const DAY_MS = 86_400_000;
  const HOUR_MS = 3_600_000;
  const pad = (n) => String(n).padStart(2, '0');
  const APPLIANCES = ['fridge', 'heat_pump_space_heating', 'heat_pump_hot_water', 'kettle', 'coffee_machine', 'oven',
    'washing_machine', 'dishwasher', 'tv', 'laptop', 'wifi_router', 'lighting', 'phone_tablet_charging', 'standby'];
  const HUMAN = { fridge: 'the fridge', heat_pump_space_heating: 'space heating', heat_pump_hot_water: 'hot water',
    kettle: 'the kettle', coffee_machine: 'the coffee machine', oven: 'the oven', washing_machine: 'the washing machine',
    dishwasher: 'the dishwasher', tv: 'the TV', laptop: 'the laptop', wifi_router: 'the router', lighting: 'lighting',
    phone_tablet_charging: 'device charging', standby: 'standby devices' };

  const text = (path) => fetch(path, { cache: 'no-cache' }).then((r) => {
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.text();
  });
  const table = (csv) => {
    const [head, ...lines] = csv.trim().split('\n');
    const cols = head.split(',');
    return lines.map((l) => l.split(','))
      .map((cells) => Object.fromEntries(cols.map((c, i) => [c, cells[i]])));
  };
  const soft = (promise, what) => promise.catch((err) => {
    console.warn(`${what} not loaded (${err.message})`);
    return null;
  });

  // ---- wrap-around ----
  /** Hour of the (wall-clock) year 2026 for a date of any year: the row index of the hourly files. */
  const hourIndex = (d) => {
    const day = d.getMonth() === 1 && d.getDate() === 29 ? 28 : d.getDate();
    return ((Date.UTC(YEAR, d.getMonth(), day) - Date.UTC(YEAR, 0, 1)) / DAY_MS) * 24 + d.getHours();
  };
  const wrapHour = (h) => ((h % HOURS) + HOURS) % HOURS;
  /** ISO date (YYYY-MM-DD) of 2026 for a date of any year. */
  const canonicalDay = (d) => {
    const day = d.getMonth() === 1 && d.getDate() === 29 ? 28 : d.getDate();
    return `${YEAR}-${pad(d.getMonth() + 1)}-${pad(day)}`;
  };

  const sources = {
    hourly: soft(text(HW.config.dataUrls.consumption).then(table), 'Consumption'),
    weather: soft(text(HW.config.dataUrls.weather).then(table), 'Weather'),
    positions: soft(text(HW.config.dataUrls.positions).then(table), 'Positions'),
    calendar: soft(text(HW.config.dataUrls.calendar).then((ics) => parseIcs(ics)), 'Calendar'),
  };

  /** All-day calendar entries as { date: 'YYYY-MM-DD' -> [{ summary, cat, location }] } (multi-day entries on every day). */
  function parseIcs(ics) {
    const lines = ics.replace(/\r\n/g, '\n').replace(/\n[ \t]/g, '').split('\n');
    const days = {};
    let ev = null;
    for (const line of lines) {
      if (line === 'BEGIN:VEVENT') ev = {};
      else if (line === 'END:VEVENT') {
        if (ev.allDay) {
          for (let t = ev.start; t < ev.end; t += DAY_MS) {
            const d = new Date(t);
            const key = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
            (days[key] ??= []).push({ summary: ev.summary, cat: ev.cat, location: ev.location, first: ev.start, last: ev.end - DAY_MS });
          }
        }
        ev = null;
      } else if (ev) {
        const i = line.indexOf(':');
        const key = line.slice(0, i).split(';')[0];
        const val = line.slice(i + 1);
        const unesc = (s) => s.replace(/\\([,;\\])/g, '$1').replace(/\\n/gi, ' ');
        if (key === 'DTSTART' && !val.includes('T')) { ev.allDay = true; ev.start = Date.UTC(+val.slice(0, 4), +val.slice(4, 6) - 1, +val.slice(6, 8)); }
        if (key === 'DTEND' && !val.includes('T')) ev.end = Date.UTC(+val.slice(0, 4), +val.slice(4, 6) - 1, +val.slice(6, 8));
        if (key === 'SUMMARY') ev.summary = unesc(val);
        if (key === 'CATEGORIES') ev.cat = val;
        if (key === 'LOCATION') ev.location = unesc(val);
      }
    }
    return days;
  }

  const distanceM = (a, b) => {
    const k = 111320;
    return Math.hypot((a.lat - b.lat) * k, (a.lon - b.lon) * k * Math.cos((a.lat * Math.PI) / 180));
  };

  /** The view of the data for one moment `now` (a Date in any year). */
  async function at(now) {
    const [hourly, weather, positions, calendar] = await Promise.all(Object.values(sources));
    const idx = hourIndex(now);
    const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const label = (d) => `${d.getDate()} ${d.toLocaleString('en-US', { month: 'short' })}`;

    // the metered hours of the 30 days before now: row i is `idx - k` hours back
    const window = (rows, perHour = 1) => {
      const out = [];
      for (let k = WINDOW_DAYS * 24; k >= 1; k--) out.push({ back: k, date: new Date(now.getTime() - k * HOUR_MS), row: rows[wrapHour(idx - k)] });
      return out;
    };
    const total = (row) => APPLIANCES.reduce((s, a) => s + Number(row[`${a}_kwh`]), 0);

    return {
      available: { consumption: !!hourly, weather: !!weather, positions: !!positions, calendar: !!calendar },

      /** kWh per day for the last `days` full days before today (oldest first) with their labels. */
      dailyTotals(days = 28) {
        if (!hourly) return null;
        const sums = [];
        const first = new Date(startOfDay.getTime() - days * DAY_MS);
        for (let d = 0; d < days; d++) {
          const day = new Date(first.getFullYear(), first.getMonth(), first.getDate() + d);
          let kwh = 0;
          for (let h = 0; h < 24; h++) kwh += total(hourly[wrapHour(hourIndex(new Date(day.getFullYear(), day.getMonth(), day.getDate(), h)))]);
          sums.push({ label: label(day), kwh });
        }
        return sums;
      },

      /** Average kWh per hour of day on the weekdays inside the 30-day window, and the busiest 4 consecutive hours. */
      peakHours() {
        if (!hourly) return null;
        const per = Array.from({ length: 24 }, () => []);
        const used = {};
        const rows = window(hourly).filter((w) => w.date.getDay() % 6 !== 0);
        for (const { date, row } of rows) per[date.getHours()].push(total(row));
        const hours = per.map((v) => (v.length ? v.reduce((s, x) => s + x, 0) / v.length : 0));
        let from = 0;
        for (let h = 0; h < 21; h++) if (hours.slice(h, h + 4).reduce((s, x) => s + x, 0) > hours.slice(from, from + 4).reduce((s, x) => s + x, 0)) from = h;
        for (const { date, row } of rows) {
          if (date.getHours() >= from && date.getHours() < from + 4) for (const a of APPLIANCES) used[a] = (used[a] ?? 0) + Number(row[`${a}_kwh`]);
        }
        const top = Object.keys(used).sort((a, b) => used[b] - used[a]).slice(0, 2).map((a) => HUMAN[a]);
        return { hours: hours.map((v) => Math.round(v * 1000) / 1000), from, to: from + 3,
          text: `Your highest energy demand is typically between ${from}–${from + 4} h on weekdays, mostly ${top.join(' and ')}.` };
      },

      /** Outdoor conditions at the home location in the current hour. */
      weather() {
        const r = weather?.[wrapHour(idx)];
        return r ? { temperature: Number(r.temp_out_c), humidity: Number(r.relative_humidity_pct) } : null;
      },

      /** Where the phone was at the last fix: { home, km, minutesAgo }. */
      presence() {
        if (!positions) return null;
        const i = wrapHour(idx) * 4 + Math.floor(now.getMinutes() / 15);
        const r = positions[Math.min(i, positions.length - 1)];
        const d = distanceM({ lat: Number(r.lat), lon: Number(r.lon) }, HW.config.home);
        return { home: d < 150, km: d / 1000 };
      },

      /** Today's plan and the next trip from the calendar. */
      agenda() {
        if (!calendar) return null;
        const key = canonicalDay(now);
        const today = calendar[key] ?? [];
        const mode = today.find((e) => e.cat === 'OFFICE' || e.cat === 'WFH' || e.cat.startsWith('TRAVEL'));
        const dayNumber = (k) => Date.UTC(+k.slice(0, 4), +k.slice(5, 7) - 1, +k.slice(8)) / DAY_MS;
        let next = null;
        for (let n = 1; n <= 60 && !next; n++) {            // the year is circular: after 31 Dec comes 1 Jan
          const d = new Date(startOfDay.getFullYear(), startOfDay.getMonth(), startOfDay.getDate() + n);
          const trip = (calendar[canonicalDay(d)] ?? []).find((e) => e.cat.startsWith('TRAVEL') && e.first === Date.UTC(YEAR, d.getMonth(), d.getDate()));
          if (trip) next = { in: n, place: trip.location.split(',')[0], summary: trip.summary };
        }
        const traveling = mode?.cat.startsWith('TRAVEL');
        return { today: mode ? (traveling ? `Travelling – ${mode.location.split(',')[0]}` : mode.cat === 'OFFICE' ? 'Office day' : 'Working from home') : 'No work plans', next };
      },
    };
  }

  HW.dataset = { at, canonicalDay, hourIndex, YEAR, WINDOW_DAYS };
})();
