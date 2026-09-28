/* Global Alpine state (navigation) + magic helpers shared by all screens.
   The current screen is mirrored in the URL hash (#usage, #devices …): deep links + browser back work. */
document.addEventListener('alpine:init', () => {
  const screens = ['home', 'forecast', 'profile'];
  const aliases = { usage: 'forecast', devices: 'forecast' };   // old deep links
  const fromHash = () => {
    const id = location.hash.slice(1);
    return screens.includes(aliases[id] || id) ? aliases[id] || id : 'home';
  };

  Alpine.store('nav', {
    screen: fromHash(),
    tabs: HW.config.tabs,
    go(screen) {
      if (screen !== this.screen) location.hash = screen;   // hashchange updates `screen`
    },
    get activeTab() {
      return this.screen;
    },
  });

  if (new URLSearchParams(location.search).has('full')) {
    document.querySelector('.phone')?.classList.add('full');
  }

  // Screen changes are animated with the View Transitions API so it is clear where a page comes from:
  //  - screens slide in the direction of the tab order (Home → Forecast pushes in from the right, going back
  //    to Home pops it out to the right),
  // Browsers without the API just switch instantly.
  const direction = (from, to) => {
    const order = HW.config.tabs.map((t) => t.id);
    return order.indexOf(to) > order.indexOf(from) ? 'forward' : 'back';
  };

  const show = (next) => {
    const nav = Alpine.store('nav');
    const prev = nav.screen;
    if (next === prev) return;
    const apply = async () => {
      nav.screen = next;
      await Alpine.nextTick();
      document.querySelector('.screen')?.scrollTo({ top: 0 });
    };
    if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) {
      apply();
      return;
    }
    const classes = [`vt-${direction(prev, next)}`];
    const root = document.documentElement;
    root.classList.add(...classes);
    document.startViewTransition(apply).finished.finally(() => root.classList.remove(...classes));
  };

  window.addEventListener('hashchange', () => show(fromHash()));

  // Fake "current time": the system clock shifted by a persisted offset (0 until the user sets a time), so it
  // keeps running. `now` is refreshed every 10 s, which updates the status bar and every "now" indicator.
  const OFFSET_KEY = 'hw.clockOffset';
  const PROFILE_KEY = 'hw.profile';
  const TICK_MS = 10_000;
  const pad = (n) => String(n).padStart(2, '0');
  const toLocalIso = (d) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const valid = (iso) => /^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(iso || '') && !isNaN(new Date(iso));
  const loadOffset = () => {
    try {
      const saved = Number(localStorage.getItem(OFFSET_KEY));
      if (Number.isFinite(saved)) return saved;
    } catch { /* storage unavailable: run on the system time */ }
    return 0;
  };

  Alpine.store('clock', {
    offset: loadOffset(),
    now: Date.now(),
    start() {
      setInterval(() => { this.now = Date.now(); }, TICK_MS);
    },
    /** Jump to a time picked as local 'YYYY-MM-DDTHH:mm'; it keeps running from there. */
    set(iso) {
      if (!valid(iso)) return;
      this.now = Date.now();
      this.offset = new Date(iso).getTime() - this.now;
      try { localStorage.setItem(OFFSET_KEY, String(this.offset)); } catch { /* ignore */ }
    },
    get date() { return new Date(this.now + this.offset); },
    get iso() { return toLocalIso(this.date); },
    /** Minutes since 00:00 (0 … 1439): the position on any 00:00–23:59 day axis. */
    get minutes() { return this.date.getHours() * 60 + this.date.getMinutes(); },
    /** Status-bar style time, e.g. "9:41" or "14:30" */
    get time() { return `${this.date.getHours()}:${pad(this.date.getMinutes())}`; },
    /** e.g. "Sep 28, 2026 14:30" */
    get label() {
      const d = this.date;
      return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    },
  });
  Alpine.store('clock').start();

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
