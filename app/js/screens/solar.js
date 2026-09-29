/* Solar potential: what a share of a community PV rooftop would do for her, from src/simulate_pv.py
   (data/app/pv_simulation.json). Scenario A = as she lives now, B = with shifting washer, dishwasher and hot water
   to the best hours. The store is shared by the Solar screen, the Home card and the Profile row. */
document.addEventListener('alpine:init', () => {

  Alpine.store('solar', {
    meta: null, sizes: [], kwp: null,
    scenario: 'B',                 // year chart + summary: 'A' currently, 'B' with shifting (toggle in the chart card)

    async init() {
      const sim = await HW.api.getPvSimulation();
      if (!sim) return;
      this.meta = sim.meta;
      this.sizes = sim.sizes;
      this.kwp = this.best?.kwp ?? 1;
    },

    get ready() { return this.sizes.length > 0; },
    /** Sizes that can be picked (0 kWp only serves as the "shifting alone" reference). */
    get options() { return this.sizes.filter((r) => r.kwp > 0).map((r) => r.kwp); },
    /** The size with the shortest payback when she also shifts (scenario B). */
    get best() {
      return this.sizes.filter((r) => r.B.payback_years).sort((a, b) => a.B.payback_years - b.B.payback_years)[0] ?? null;
    },
    get current() { return this.sizes.find((r) => r.kwp === this.kwp) ?? null; },
    /** Results of the chosen size in the chosen scenario. */
    get view() { return this.current?.[this.scenario] ?? null; },
    /** What shifting alone (no PV) saves per year: part of every scenario B saving. */
    get shiftingAlone() { return this.sizes.find((r) => r.kwp === 0)?.B.saving ?? 0; },
  });

  Alpine.data('solarScreen', () => ({
    get s() { return Alpine.store('solar'); },

    /** At a glance: one row per figure – without solar, as you live now, with shifting (+ the gain of shifting). */
    get rows() {
      const r = this.s.current;
      if (!r) return [];
      const { A: a, B: b } = r;
      const pct = (x) => `${Math.round(x * 100)} %`;
      const years = (x) => (x ? `${x.toFixed(1)} y` : '–');
      const pp = Math.round((b.self_sufficiency - a.self_sufficiency) * 100);
      const eur = Math.round(b.saving - a.saving);
      const dy = a.payback_years && b.payback_years ? a.payback_years - b.payback_years : 0;
      return [
        { label: 'Covered', hint: 'of your consumption', none: '0 %', now: pct(a.self_sufficiency), shift: pct(b.self_sufficiency),
          gain: pp > 0 ? `+${pp} %` : '' },
        { label: 'Saved', hint: 'per year', none: '€0', now: `€${Math.round(a.saving)}`, shift: `€${Math.round(b.saving)}`,
          gain: eur > 0 ? `+€${eur}` : '' },
        { label: 'Payback', hint: 'years', none: '–', now: years(a.payback_years), shift: years(b.payback_years),
          gain: dy > 0 ? `−${dy.toFixed(1)} y` : '' },
      ];
    },
    /** One sentence on what shifting adds at the chosen size (only in "With shifting"). */
    get gain() {
      const r = this.s.current;
      if (!r) return '';
      const eur = Math.round(r.B.saving - r.A.saving);
      const kwh = Math.round(r.B.used - r.A.used);
      return `Shifting the washer, dishwasher and hot water to sunny or cheap hours adds ≈ €${eur} a year: ` +
             `you use ${kwh} kWh more of your own solar power.`;
    },
    get summary() {
      const r = this.s.current;
      const v = this.s.view;
      if (!r || !v) return '';
      return `A ${r.kwp} kWp share (€${r.investment.toLocaleString('en-US')}) produces ${Math.round(r.production).toLocaleString('en-US')} kWh a year. ` +
             `You would use ${Math.round(v.used)} kWh of it yourself – that much less bought from the grid, ` +
             `${Math.round(v.self_sufficiency * 100)} % of your consumption – and ${Math.round(v.export)} kWh go to the grid at €0.08.`;
    },
    get monthlySpec() { return this.s.view ? HW.charts.solarMonthly(this.s.view.monthly.map((m) => ({ ...m }))) : null; },
    get sizesSpec() { return this.s.ready ? HW.charts.solarSizes(structuredClone(Alpine.raw(this.s.sizes)), this.s.kwp) : null; },
    get shiftNote() {
      return `Shifting alone (without PV) already saves ≈ €${Math.round(this.s.shiftingAlone)} a year; it is included in “With shifting”.`;
    },
    get sourceNote() {
      const m = this.s.meta;
      return m ? `${m.source} · ${m.yield_kwh_per_kwp} kWh per kWp in Warsaw · €${m.cost_per_kwp}/kWp · export €${m.export_price}/kWh · ` +
                 `operating cost ${m.operating_cost_share * 100} %/year · your share counted hour by hour on your meter.` : '';
    },
  }));

  // Home card: the best option at a glance with the year overview in small.
  Alpine.data('solarCard', () => ({
    get s() { return Alpine.store('solar'); },
    get headline() {
      const b = this.s.best;
      return b ? `A ${b.kwp} kWp share of a community rooftop would pay back in ${b.B.payback_years.toFixed(1)} years` : '';
    },
    get facts() {
      const b = this.s.best;
      return b ? [`${Math.round(b.B.self_sufficiency * 100)} % of your consumption`, `≈ €${Math.round(b.B.saving)} saved per year`] : [];
    },
    get spec() { return this.s.best ? HW.charts.solarMonthly(this.s.best.B.monthly.map((m) => ({ ...m })), { compact: true }) : null; },
  }));
});
