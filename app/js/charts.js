/* Chart.js (vendored in vendor/chartjs) wrappers. Chart.js must never see Alpine's reactive proxies (it writes
   to the data it is given, which would re-trigger the chart's effect in a loop), hence the copies and Alpine.raw.
   Each function below turns screen data into a
   { config, ready } spec that the `x-chart` directive mounts on a <canvas>. Colors come from the CSS tokens,
   so the charts follow the app's color scheme. */
(() => {
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const theme = () => ({
    accent: token('--accent'), line: token('--line'), card: token('--card'),
    bar: '#3c3a38', barHover: '#5a5755', forecast: '#6f6c69', text: '#c8c4bf',
  });

  Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
  Chart.defaults.color = token('--muted');

  const tooltip = (t) => ({
    backgroundColor: '#211f1d', borderColor: t.accent, borderWidth: 1.5, cornerRadius: 14,
    padding: { x: 14, y: 9 }, displayColors: false, caretSize: 6, caretPadding: 10, boxPadding: 0,
    titleColor: t.accent, titleFont: { size: 15, weight: '600' }, titleMarginBottom: 3,
    bodyColor: t.text, bodyFont: { size: 13 },
  });

  /** Hidden x axis; y axis reduced to three faint gridlines. */
  const scales = (t, y = {}) => ({
    x: { display: false },
    y: { grid: { color: t.line, drawTicks: false }, border: { display: false }, ticks: { display: false, count: 3 }, ...y },
  });

  const base = (t, extra = {}) => ({
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'nearest', axis: 'x', intersect: false },
    plugins: { legend: { display: false }, tooltip: tooltip(t) },
    ...extra,
  });

  HW.charts = {
    /** Home: actual + forecast lines sharing one axis; the last actual point is "now". */
    overview({ actual, forecast, pointLabels }) {
      const t = theme();
      const nulls = Array(actual.length - 1).fill(null);
      const last = actual.length - 1;
      const dataset = (label, data, color, extra) => ({
        label, data, borderColor: color, borderWidth: 3, tension: 0, cubicInterpolationMode: 'monotone',
        pointRadius: 0, pointHoverRadius: 6, pointHoverBackgroundColor: color, pointHoverBorderWidth: 0, ...extra,
      });
      return { config: {
        type: 'line',
        data: {
          labels: pointLabels ?? [...actual, ...forecast].map(() => ''),
          datasets: [
            dataset('Actual', [...actual, ...Array(forecast.length).fill(null)], t.accent, {
              pointRadius: (c) => (c.dataIndex === last ? 8 : 0), pointBackgroundColor: t.accent,
              pointBorderColor: 'rgba(255, 176, 102, .18)', pointBorderWidth: 5, pointHoverBorderWidth: 5,
              pointHoverBorderColor: 'rgba(255, 176, 102, .18)',
            }),
            dataset('Forecast', [...nulls, actual[last], ...forecast], t.forecast, { borderDash: [5, 6] }),
          ],
        },
        options: base(t, {
          layout: { padding: { top: 8, bottom: 8, left: 8, right: 8 } },
          scales: scales(t, { grace: '15%' }),
          plugins: { legend: { display: false }, tooltip: { ...tooltip(t), callbacks: {
            title: (items) => items[0].label || 'Average per day',
            label: (item) => `${item.dataset.label}: ${item.parsed.y.toFixed(1)} kWh`,
          } } },
        }),
      } };
    },

    /** Energy Usage screen: profile line; highlighted points are ringed and show their story in the tooltip. */
    profile({ values, highlights }, { start, stepHours } = {}) {
      const t = theme();
      const byIndex = new Map(highlights.map((h) => [h.index, h]));
      const when = (i) => (start && stepHours
        ? new Date(start.getTime() + i * stepHours * 3600_000).toLocaleString('en-US', {
          weekday: 'short', day: 'numeric', month: 'short',
          ...(stepHours < 24 && { hour: '2-digit', minute: '2-digit', hour12: false }),   // daily totals: date only
        })
        : '');
      const state = { selected: null };
      let peak = null;                                   // pre-selected: the highest highlighted point
      highlights.forEach((h) => { if (peak === null || values[h.index] > values[peak]) peak = h.index; });
      state.selected = peak;

      const show = (chart) => {
        if (state.selected === null) return;
        const el = chart.getDatasetMeta(0).data[state.selected];
        if (!el) return;
        const active = [{ datasetIndex: 0, index: state.selected }];
        chart.setActiveElements(active);
        const { x, y } = el.getProps(['x', 'y'], true);   // final position, not the mid-animation one
        chart.tooltip.setActiveElements(active, { x, y });
      };
      const isSelected = (c) => c.dataIndex === state.selected;

      return {
        ready(chart) {           // show the selected tooltip once the entrance animation is done
          setTimeout(() => {
            if (Chart.getChart(chart.canvas) === chart && !chart.tooltip.getActiveElements().length) {
              show(chart);
              chart.update('none');
            }
          }, 1100);
        },
        config: {
          type: 'line',
          data: { labels: values.map((_, i) => i), datasets: [{
            data: [...values], borderColor: t.accent, borderWidth: 3, cubicInterpolationMode: 'monotone',
            pointRadius: (c) => (byIndex.has(c.dataIndex) ? 8 : 0),
            pointHoverRadius: (c) => (byIndex.has(c.dataIndex) ? 9 : 5),
            pointBackgroundColor: (c) => (isSelected(c) ? '#fff' : t.card),
            pointHoverBackgroundColor: (c) => (byIndex.has(c.dataIndex) ? '#fff' : t.accent),
            pointBorderColor: t.accent, pointBorderWidth: 2, pointHoverBorderColor: t.accent, pointHoverBorderWidth: 2,
          }] },
          options: base(t, {
            layout: { padding: { top: 66, bottom: 10, left: 12, right: 12 } },
            scales: scales(t, { grace: '10%' }),
            onClick(evt, _els, chart) {
              const hit = chart.getElementsAtEventForMode(evt, 'nearest', { axis: 'x', intersect: false }, true)[0];
              if (hit && byIndex.has(hit.index)) { state.selected = hit.index; chart.update('none'); }
            },
            plugins: { legend: { display: false }, tooltip: { ...tooltip(t), yAlign: 'bottom', callbacks: {
              title: (items) => byIndex.get(items[0].dataIndex)?.title ?? when(items[0].dataIndex),
              label: (item) => byIndex.get(item.dataIndex)?.detail ?? `${item.parsed.y.toFixed(2)} kWh`,
            } } },
          }),
          plugins: [{
            id: 'restoreSelection',                       // when the pointer leaves, show the selected point again
            afterEvent(chart, args) {
              if (args.event.type === 'mouseout') { show(chart); args.changed = true; }
            },
          }],
        },
      };
    },

    /** Home: average kWh per hour of day; peak hours in the accent color. */
    hourly({ hours, from, to }) {
      const t = theme();
      const hot = (c) => c.dataIndex >= from && c.dataIndex <= to;
      const hh = (h) => String(h % 24).padStart(2, '0');
      return { config: {
        type: 'bar',
        data: { labels: hours.map((_, h) => h), datasets: [{
          data: [...hours], barPercentage: .8, categoryPercentage: 1,
          borderRadius: { topLeft: 5, topRight: 5, bottomLeft: 3, bottomRight: 3 }, borderSkipped: false,
          backgroundColor: (c) => (hot(c) ? t.accent : t.bar),
          hoverBackgroundColor: (c) => (hot(c) ? '#ffc48f' : t.barHover),
        }] },
        options: base(t, {
          layout: { padding: 0 },
          scales: { x: { display: false }, y: { display: false, min: 0 } },
          plugins: { legend: { display: false }, tooltip: { ...tooltip(t), callbacks: {
            title: (items) => `${hh(items[0].dataIndex)}:00–${hh(items[0].dataIndex + 1)}:00`,
            label: (item) => `${item.parsed.y.toFixed(2)} kWh${hot(item) ? ' · peak' : ''}`,
          } } },
        }),
      } };
    },
  };

  /** x-chart="spec": (re)creates a Chart.js chart on this <canvas> whenever the spec changes. */
  document.addEventListener('alpine:init', () => {
    Alpine.directive('chart', (el, { expression }, { evaluateLater, effect, cleanup }) => {
      const get = evaluateLater(expression);
      let chart = null;
      effect(() => get((proxied) => {
        const spec = proxied && Alpine.raw(proxied);       // Alpine wraps getter results in reactive proxies
        chart?.destroy();
        chart = null;
        if (!spec) return;
        chart = new Chart(el, spec.config);
        spec.ready?.(chart);
      }));
      cleanup(() => chart?.destroy());
    });
  });
})();
