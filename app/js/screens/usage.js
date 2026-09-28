/* Energy Usage: 24h / 3d / 7d profile with highlighted points, incidents and summary. */
document.addEventListener('alpine:init', () => {
  const BOX = { width: 300, height: 150, pad: 20 };

  Alpine.data('usageScreen', () => ({
    ranges: HW.config.ranges,
    range: '7d',
    data: null,
    selected: null,      // index into data.highlights

    async init() {
      await this.load();
    },

    async setRange(range) {
      this.range = range;
      await this.load();
    },

    async load() {
      this.data = await HW.api.getUsage(this.range);
      // pre-select the highest highlighted point (like the tooltip in the mockup)
      const hl = this.data.highlights;
      this.selected = hl.length ? hl.indexOf(hl.reduce((a, b) =>
        this.data.values[b.index] > this.data.values[a.index] ? b : a)) : null;
    },

    get chart() {
      if (!this.data) return { path: '', markers: [] };
      const points = HW.charts.scale(this.data.values, BOX);
      const markers = this.data.highlights.map((h) => ({
        ...h,
        point: points[h.index],
        style: HW.charts.position(points[h.index], BOX.width, BOX.height),
      }));
      return { path: HW.charts.path(points), markers };
    },

    get tooltip() {
      const m = this.selected === null ? null : this.chart.markers[this.selected];
      if (!m) return null;
      const left = Math.min(72, Math.max(28, (m.point.x / BOX.width) * 100));
      const top = (m.point.y / BOX.height) * 100;
      return { ...m, style: `left:${left}%;top:${top}%` };
    },
  }));
});
