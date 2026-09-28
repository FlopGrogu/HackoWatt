/* Energy Usage: 24h / 3d / 7d profile with highlighted points, incidents and summary. */
document.addEventListener('alpine:init', () => {
  Alpine.data('usageScreen', () => ({
    ranges: HW.config.ranges,
    range: '7d',
    data: null,

    async init() {
      await this.load();
    },

    async setRange(range) {
      this.range = range;
      await this.load();
    },

    async load() {
      this.data = await HW.api.getUsage(this.range);
    },

    get profileSpec() {
      return this.data && HW.charts.profile(this.data);
    },
  }));
});
