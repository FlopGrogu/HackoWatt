/* Global Alpine state (navigation) + magic helpers shared by all screens.
   The current screen is mirrored in the URL hash (#usage, #devices …): deep links + browser back work. */
document.addEventListener('alpine:init', () => {
  const screens = ['home', 'usage', 'devices', 'profile'];
  const parentTab = { usage: 'home' };        // sub-screens highlight the tab they belong to
  const fromHash = () => {
    const id = location.hash.slice(1);
    return screens.includes(id) ? id : 'home';
  };

  Alpine.store('nav', {
    screen: fromHash(),
    tabs: HW.config.tabs,
    go(screen) {
      if (screen !== this.screen) location.hash = screen;   // hashchange updates `screen`
    },
    get activeTab() {
      return parentTab[this.screen] || this.screen;
    },
  });

  if (new URLSearchParams(location.search).has('full')) {
    document.querySelector('.phone')?.classList.add('full');
  }

  window.addEventListener('hashchange', () => {
    Alpine.store('nav').screen = fromHash();
    document.querySelector('.screen')?.scrollTo({ top: 0 });
  });

  // Fake "current time": initialised from the system clock once, then persisted in localStorage.
  // Stored as local 'YYYY-MM-DDTHH:mm' (the format of <input type="datetime-local">).
  const CLOCK_KEY = 'hw.fakeTime';
  const PROFILE_KEY = 'hw.profile';
  const pad = (n) => String(n).padStart(2, '0');
  const toLocalIso = (d) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const valid = (iso) => /^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(iso || '') && !isNaN(new Date(iso));
  const loadClock = () => {
    try {
      const saved = localStorage.getItem(CLOCK_KEY);
      if (valid(saved)) return saved;
    } catch { /* storage unavailable: fall through to the system time */ }
    const iso = toLocalIso(new Date());
    try { localStorage.setItem(CLOCK_KEY, iso); } catch { /* ignore */ }
    return iso;
  };

  Alpine.store('clock', {
    iso: loadClock(),
    set(iso) {
      if (!valid(iso)) return;
      this.iso = iso;
      try { localStorage.setItem(CLOCK_KEY, iso); } catch { /* ignore */ }
    },
    get date() { return new Date(this.iso); },
    /** Minutes since 00:00 (0 … 1439): the position on any 00:00–23:59 day axis. */
    get minutes() { return this.date.getHours() * 60 + this.date.getMinutes(); },
    /** e.g. "Sep 28, 2026 14:30" */
    get label() {
      const d = this.date;
      return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    },
  });

  // Account + location, persisted across sessions.
  const DEFAULT_PROFILE = {
    name: 'Aleksandra',
    email: 'aleksandra.home@energy.io',
    location: { name: 'Warsaw, Poland', lat: 52.2298, lon: 21.0118 },
  };
  const loadProfile = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(PROFILE_KEY));
      if (saved && typeof saved === 'object') {
        return { ...DEFAULT_PROFILE, ...saved, location: { ...DEFAULT_PROFILE.location, ...saved.location } };
      }
    } catch { /* corrupt or unavailable: use defaults */ }
    return structuredClone(DEFAULT_PROFILE);
  };

  Alpine.store('profile', {
    ...loadProfile(),
    get initials() { return (this.name.trim()[0] || '?').toUpperCase(); },
    save() {
      const { name, email, location } = this;
      try { localStorage.setItem(PROFILE_KEY, JSON.stringify({ name, email, location })); } catch { /* ignore */ }
    },
    setLocation(location) {
      this.location = location;
      this.save();
    },
  });

  Alpine.magic('icon', () => (name) => HW.icons[name] || '');
  Alpine.magic('euro', () => (value) => `${HW.config.currency}${value.toFixed(2)}`);
});
