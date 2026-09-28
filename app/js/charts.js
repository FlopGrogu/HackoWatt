/* Pure chart helpers: turn number series into SVG path strings / CSS positions.
   Charts are drawn in an SVG viewBox (width × height) stretched to the card; markers are HTML elements
   positioned in %, so they stay round when the SVG is stretched. */
HW.charts = {
  /** Scale values to [top, bottom] of the viewBox. Returns [{x, y}] in viewBox units. */
  scale(values, { width, height, pad = 12, count = values.length, offset = 0, min, max }) {
    const lo = min ?? Math.min(...values);
    const hi = max ?? Math.max(...values);
    const span = hi - lo || 1;
    const step = count > 1 ? width / (count - 1) : 0;
    return values.map((v, i) => ({
      x: (offset + i) * step,
      y: pad + (1 - (v - lo) / span) * (height - 2 * pad),
    }));
  },

  /** SVG path "M x y L x y …" through the points. */
  path(points) {
    return points.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  },

  /** CSS left/top in % for an HTML marker on a point of a viewBox of size width × height. */
  position(point, width, height) {
    return `left:${(point.x / width) * 100}%;top:${(point.y / height) * 100}%`;
  },

  /**
   * Actual + forecast line sharing one scale: the forecast starts at the last actual point.
   * Returns { actual, forecast, last } (paths as strings, last = point of "now").
   */
  actualAndForecast(actual, forecast, box) {
    const all = [...actual, ...forecast];
    const opts = { ...box, count: all.length, min: Math.min(...all), max: Math.max(...all) };
    const a = this.scale(actual, opts);
    const f = this.scale([actual[actual.length - 1], ...forecast], { ...opts, offset: actual.length - 1 });
    return { actual: this.path(a), forecast: this.path(f), last: a[a.length - 1] };
  },
};
