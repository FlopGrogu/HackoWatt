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

  // Hover mode of the profile chart: a shift marker wins when the pointer is on it, otherwise the nearest
  // forecast point along x (so the dashed alternative line does not steal the regular tooltips).
  Chart.Interaction.modes.hw = (chart, e, options, useFinalPosition) => {
    const modes = Chart.Interaction.modes;
    const marker = modes.nearest(chart, e, { intersect: true }, useFinalPosition).filter((el) => el.datasetIndex === 1);
    if (marker.length) return marker;
    return modes.nearest(chart, e, { axis: 'x', intersect: false }, useFinalPosition).filter((el) => el.datasetIndex === 0);
  };

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

    /**
     * Forecast profile: the predicted kWh per block. Highlighted points are ringed and explain themselves in the
     * tooltip. Scheduling a shiftable device moves its energy, so the line is `values` plus the deltas of the
     * confirmed shifts; pending (not yet confirmed) shifts are drawn as a dashed green alternative line with a
     * clickable marker at the cheaper time. `shifts` = { pending, confirmed }, `onPick(shift)` = marker clicked.
     */
    profile({ values, highlights }, { start, stepHours, shifts = {}, onPick } = {}) {
      const t = theme();
      const green = token('--green');
      const step = stepHours || 1;
      const count = values.length;
      const { pending = [], confirmed = [] } = shifts;

      // --- apply shifts: {hour offset: kWh} maps are added to / removed from the block containing that hour ---
      const bucketed = (shift) => {
        const delta = Array(count).fill(0);
        const put = (map, sign) => Object.entries(map).forEach(([hour, kwh]) => {
          const b = Math.floor(hour / step);
          if (b < count) delta[b] += sign * kwh;
        });
        put(shift.adds, 1);
        put(shift.removes, -1);
        return delta;
      };
      const apply = (series, list) => list.reduce((acc, sh) => acc.map((v, i) => v + bucketed(sh)[i]), series);
      const main = apply([...values], confirmed);
      const alt = apply(main, pending);
      const near = (i) => [i - 1, i, i + 1].some((j) => Math.abs((alt[j] ?? main[j]) - main[j]) > 1e-9);
      const altData = pending.length ? alt.map((v, i) => (near(i) ? v : null)) : alt.map(() => null);
      const markers = new Map(pending.map((sh) => [Math.floor(sh.idealIndex / step), sh])
        .filter(([b]) => b < count));

      const byIndex = new Map(highlights.map((h) => [h.index, h]));
      const when = (i) => (start && stepHours
        ? new Date(start.getTime() + i * stepHours * 3600_000).toLocaleString('en-US', {
          weekday: 'short', day: 'numeric', month: 'short',
          ...(stepHours < 24 && { hour: '2-digit', minute: '2-digit', hour12: false }),   // daily totals: date only
        })
        : '');
      const at = (iso) => new Date(iso).toLocaleString('en-US', { weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
      const wrap = (text, width = 34) => text.split(' ').reduce((lines, word) => {   // canvas text does not wrap
        const last = lines[lines.length - 1];
        if (last && (last + ' ' + word).length <= width) lines[lines.length - 1] = `${last} ${word}`;
        else lines.push(word);
        return lines;
      }, []);

      const state = { selected: null };
      let peak = null;                                   // pre-selected: the highest highlighted point
      highlights.forEach((h) => { if (peak === null || main[h.index] > main[peak]) peak = h.index; });
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
        id: `profile-${count}-${step}`,        // same id = same chart: data changes animate instead of redrawing
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
            data: main, borderColor: t.accent, borderWidth: 3, cubicInterpolationMode: 'monotone',
            pointRadius: (c) => (byIndex.has(c.dataIndex) ? 8 : 0),
            pointHoverRadius: (c) => (byIndex.has(c.dataIndex) ? 9 : 5),
            pointBackgroundColor: (c) => (isSelected(c) ? '#fff' : t.card),
            pointHoverBackgroundColor: (c) => (byIndex.has(c.dataIndex) ? '#fff' : t.accent),
            pointBorderColor: t.accent, pointBorderWidth: 2, pointHoverBorderColor: t.accent, pointHoverBorderWidth: 2,
          }, {
            data: altData, borderColor: green, borderWidth: 2.5, borderDash: [6, 5], cubicInterpolationMode: 'monotone',
            spanGaps: false, order: -1,
            pointRadius: (c) => (markers.has(c.dataIndex) ? 9 : 0),
            pointHitRadius: (c) => (markers.has(c.dataIndex) ? 18 : 0),
            pointHoverRadius: (c) => (markers.has(c.dataIndex) ? 11 : 0),
            pointBackgroundColor: t.card, pointHoverBackgroundColor: green,
            pointBorderColor: green, pointBorderWidth: 3, pointHoverBorderColor: green,
          }] },
          options: base(t, {
            layout: { padding: { top: 96, bottom: 10, left: 12, right: 12 } },
            interaction: { mode: 'hw', intersect: false },
            scales: scales(t, { grace: '10%' }),
            onClick(evt, _els, chart) {
              const alt = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true)
                .find((e) => e.datasetIndex === 1 && markers.has(e.index));
              if (alt) { onPick?.(markers.get(alt.index)); return; }
              const hit = chart.getElementsAtEventForMode(evt, 'nearest', { axis: 'x', intersect: false }, true)[0];
              if (hit && byIndex.has(hit.index)) { state.selected = hit.index; chart.update('none'); }
            },
            plugins: { legend: { display: false }, tooltip: { ...tooltip(t), callbacks: {
              title: (items) => {
                const [item] = items;
                if (item.datasetIndex === 1) return `Shift ${markers.get(item.dataIndex).device}`;
                return byIndex.get(item.dataIndex)?.title ?? when(item.dataIndex);
              },
              label: (item) => {
                if (item.datasetIndex === 1) {
                  const sh = markers.get(item.dataIndex);
                  return [`Run at ${at(sh.ideal)} instead of ${at(sh.usual)}`,
                          `Saves ≈ €${sh.saving.toFixed(2)} · tap to schedule`];
                }
                const h = byIndex.get(item.dataIndex);
                return h ? [h.detail, ...(h.explain || []).flatMap((line) => wrap(line))]
                  : `${item.parsed.y.toFixed(2)} kWh`;
              },
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
      let id = null;
      effect(() => get((proxied) => {
        const spec = proxied && Alpine.raw(proxied);       // Alpine wraps getter results in reactive proxies
        if (chart && spec?.id && spec.id === id) {         // same chart, new numbers: animate to them
          chart.data = spec.config.data;
          chart.options = spec.config.options;
          chart.update();
          return;
        }
        chart?.destroy();
        chart = null;
        id = spec?.id ?? null;
        if (!spec) return;
        chart = new Chart(el, spec.config);
        spec.ready?.(chart);
      }));
      cleanup(() => chart?.destroy());
    });
  });
})();
