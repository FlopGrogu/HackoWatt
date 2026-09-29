/* Monthly calendar: for every day whether Aleksandra is expected to be home (from the calendar). Opened from the Home week card. */
document.addEventListener('alpine:init', () => {
  // The popup with all entries of the tapped day (markup at the end of index.html, next to the other sheets).
  const GROUP = { 'TRAVEL-WORK': 'trip', 'TRAVEL-PRIVATE': 'trip', WORK: 'work', OFFICE: 'work', WFH: 'work', PAUL: 'social', 'SOCIAL-OUT': 'social',
    'GUESTS-HOME': 'social', SPORT: 'sport' };
  Alpine.store('day', {
    cell: null, events: [],
    async show(cell) {
      this.cell = cell;
      this.events = await HW.api.getDayEvents(cell.date);
    },
    close() { this.cell = null; },
    group: (e) => GROUP[e.cat] ?? 'other',
    get title() {
      return this.cell && new Date(this.cell.date).toLocaleString('en-US', { weekday: 'long', day: 'numeric', month: 'long' });
    },
  });

  const STATE_TEXT = { home: 'At home', partly: 'Out during the day', away: 'Away' };

  Alpine.data('calendarScreen', () => ({
    year: 0, month: 0, cells: [], selected: null,
    weekdays: ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
    stateText: STATE_TEXT,

    async init() {
      const today = Alpine.store('clock').date;         // the fake clock at load; changing it reloads the app
      this.year = today.getFullYear();
      this.month = today.getMonth();
      await this.load();
      this.selected = this.cells.find((c) => c.today) ?? null;
    },

    /** The reference date (the app's fake clock), shown under the title. */
    get todayLabel() {
      return `Today: ${Alpine.store('clock').date.toLocaleString('en-US', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}`;
    },
    get title() {
      return new Date(this.year, this.month, 1).toLocaleString('en-US', { month: 'long', year: 'numeric' });
    },
    async load() {
      this.cells = await HW.api.getMonthPlan(this.year, this.month);
    },
    async step(delta) {
      const d = new Date(this.year, this.month + delta, 1);
      this.year = d.getFullYear();
      this.month = d.getMonth();
      await this.load();
      this.selected = this.cells.find((c) => c.today) ?? this.cells.find((c) => c.inMonth) ?? null;
    },
    get summary() {
      const days = this.cells.filter((c) => c.inMonth);
      const n = (s) => days.filter((c) => c.state === s).length;
      return { home: n('home'), partly: n('partly'), away: n('away') };
    },
  }));
});
