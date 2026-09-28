/* Global Alpine state (navigation) + magic helpers shared by all screens.
   The current screen is mirrored in the URL hash (#usage, #devices …): deep links + browser back work. */
document.addEventListener('alpine:init', () => {
  const screens = ['home', 'usage', 'devices', 'search', 'profile'];
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

  Alpine.magic('icon', () => (name) => HW.icons[name] || '');
  Alpine.magic('euro', () => (value) => `${HW.config.currency}${value.toFixed(2)}`);
});
