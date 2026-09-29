/* Chart.js (vendored in vendor/chartjs) wrappers. Chart.js must never see Alpine's reactive proxies (it writes
   to the data it is given, which would re-trigger the chart's effect in a loop), hence the copies and Alpine.raw.
   Each function below turns screen data into a
   { config, ready } spec that the `x-chart` directive mounts on a <canvas>. Colors come from the CSS tokens,
   so the charts follow the app's color scheme. */
(() => {
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const theme = () => ({
    accent: token('--accent'), line: token('--line'), card: token('--card'),
    bar: '#3c3a38', barHover: '#5a5755', forecast: token('--forecast'), text: '#c8c4bf',
  });

  // Hover mode of the profile chart: a shift marker wins when the pointer is on it, otherwise the nearest
  // forecast point along x (so the dashed alternative line does not steal the regular tooltips).
  Chart.Interaction.modes.hw = (chart, e, options, useFinalPosition) => {
    const modes = Chart.Interaction.modes;
    const marker = modes.nearest(chart, e, { intersect: true }, useFinalPosition).filter((el) => el.datasetIndex === 1);
    if (marker.length) return marker;
    return modes.nearest(chart, e, { axis: 'x', intersect: false }, useFinalPosition).filter((el) => el.datasetIndex === 0);
  };

  // Vertical cursor on the profile chart at the moment the devices list is showing: options.plugins.hwCursor =
  // { startMs, step: hours per point, count }; the moment shown is Alpine.store('focus').time (else the clock). Drawn above the data, only inside the chart's range.
  Chart.register({
    id: 'hwCursor',
    afterDatasetsDraw(chart) {
      const o = chart.options.plugins.hwCursor;
      if (!o?.startMs) return;
      // read live: Chart.js caches function-valued plugin options until the next update(), which made the line lag
      const time = Alpine.store('focus').time ?? Alpine.store('clock').date.getTime();
      const i = Math.round((time - o.startMs) / (o.step * 3600_000));   // snapped to the closest data point
      if (i < 0 || i > o.count - 1) return;
      const x = chart.scales.x.getPixelForValue(i);
      const { top, bottom } = chart.chartArea;
      const { ctx } = chart;
      ctx.save();
      ctx.strokeStyle = 'rgba(255, 255, 255, .7)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();
      ctx.restore();
    },
  });

  Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
  Chart.defaults.color = token('--muted');

  // Tooltips sit above the hovered point (below it near the top edge) so they never cover it.
  Chart.Tooltip.positioners.hwAbove = function (items) {
    if (!items.length) return false;
    const { x, y } = items[0].element.tooltipPosition();
    const flip = y - this.chart.chartArea.top < 96;
    return { x, y: flip ? y + 6 : y - 6, xAlign: 'center', yAlign: flip ? 'top' : 'bottom' };
  };

  const tooltip = (t) => ({
    position: 'hwAbove', backgroundColor: '#211f1d', borderColor: `${t.accent}99`, borderWidth: 0.75, cornerRadius: 14,
    padding: { x: 14, y: 9 }, displayColors: false, caretSize: 6, caretPadding: 12, boxPadding: 0,
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
     * Forecast profile: the predicted kWh per block, over a step-function background of the tariff. Highlighted
     * points are ringed and explain themselves in the tooltip. Scheduling a shiftable device moves its energy, so
     * the line is `values` plus the deltas of the confirmed shifts; pending (not yet confirmed) shifts are drawn
     * as a dashed green alternative line with a clickable marker at the cheaper time (the forecast turns grey
     * while that alternative is on screen). `shifts` = { pending, confirmed }, `onPick(shift)` = marker clicked,
     * `onFocus(blockIndex)` = the closest data point to the pointer; the last position stays (the devices list follows it).
     */
    profile({ values, highlights, labels = [], labelIndexes }, { start, stepHours, shifts = {}, onPick, onFocus } = {}) {
      const t = theme();
      const green = token('--green');
      const step = stepHours || 1;
      const count = values.length;
      const { pending = [], confirmed = [] } = shifts;
      const line = pending.length ? t.forecast : t.accent;     // grey while the green alternative is offered

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

      // --- tariff per block (average over its hours), drawn as a step function behind the forecast ---
      const rate = (hour) => (HW.config.tariff.find((seg) => hour % 24 >= seg.from && hour % 24 < seg.to) ?? {}).price ?? 0;
      const prices = start && step < 24 ? values.map((_, i) => {        // none on the daily (7d) view
        const first = start.getHours() + i * step;
        return Array.from({ length: step }, (_, k) => rate(first + k)).reduce((a, b) => a + b, 0) / step;
      }) : null;

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

      // x-axis labels sit under the data points they belong to (index of each label in the series)
      const labelAt = new Map(labels.map((text, i) =>
        [labelIndexes?.[i] ?? Math.round((i * (count - 1)) / Math.max(labels.length - 1, 1)), text]));

      return {
        id: `profile-${count}-${step}`,        // same id = same chart: data changes animate instead of redrawing
        ready(chart) {                         // move the cursor when the hovered block / the clock changes
          Alpine.effect(() => {
            void Alpine.store('focus').time;
            void Alpine.store('clock').now;
            if (chart.canvas?.isConnected && chart.ctx) chart.draw();
          });
        },
        config: {
          type: 'line',
          data: { labels: values.map((_, i) => i), datasets: [{
            data: main, borderColor: line, borderWidth: 3, cubicInterpolationMode: 'monotone',
            pointRadius: (c) => (byIndex.has(c.dataIndex) ? 8 : 0),
            pointHoverRadius: (c) => (byIndex.has(c.dataIndex) ? 9 : 5),
            pointBackgroundColor: t.card,
            pointHoverBackgroundColor: (c) => (byIndex.has(c.dataIndex) ? '#fff' : line),
            pointBorderColor: line, pointBorderWidth: 2, pointHoverBorderColor: line, pointHoverBorderWidth: 2,
          }, {
            data: altData, borderColor: green, borderWidth: 2.5, borderDash: [6, 5], cubicInterpolationMode: 'monotone',
            spanGaps: false, order: -1,
            pointRadius: (c) => (markers.has(c.dataIndex) ? 9 : 0),
            pointHitRadius: (c) => (markers.has(c.dataIndex) ? 18 : 0),
            pointHoverRadius: (c) => (markers.has(c.dataIndex) ? 11 : 0),
            pointBackgroundColor: t.card, pointHoverBackgroundColor: green,
            pointBorderColor: green, pointBorderWidth: 3, pointHoverBorderColor: green,
          }, {
            data: prices ?? values.map(() => null), yAxisID: 'price', stepped: 'after', fill: 'origin', order: 10,
            borderColor: 'rgba(255, 255, 255, .16)', borderWidth: 1.5, backgroundColor: 'rgba(255, 255, 255, .045)',
            pointRadius: 0, pointHoverRadius: 0, pointHitRadius: 0,
          }] },
          options: base(t, {
            layout: { padding: 0 },
            interaction: { mode: 'hw', intersect: false },
            scales: {
              ...scales(t, {
                min: 0, grace: 0,                                   // nice steps, the line uses the full height
                // left-hand legend: the kWh values of the forecast line
                ticks: { display: true, count: undefined, maxTicksLimit: 5, padding: 6, color: line,   // same color as the forecast line
                         font: { size: 11 }, callback: (v) => v.toFixed(v < 10 ? 1 : 0) },
              }),
              x: {
                display: true, grid: { display: false }, border: { display: false },
                ticks: { autoSkip: false, maxRotation: 0, padding: 8, color: token('--muted'),
                         font: { size: 12 }, callback: (_v, i) => labelAt.get(i) ?? '' },
              },
              // right-hand price axis, 0–50 ct: markers show what the step background means
              price: {
                display: !!prices, position: 'right', min: 0, max: 0.5,
                grid: { display: false }, border: { display: false },
                ticks: { stepSize: 0.1, padding: 6, color: token('--muted'), font: { size: 11 }, callback: (v) => HW.fmt.money(v) },
              },
            },
            onHover(evt, _els, chart) {                      // the cursor line (and the devices list) follows the pointer
              if (evt.type === 'mouseout' || evt.x == null) return;   // leaving keeps the last position
              const { left, right } = chart.chartArea;
              const f = chart.scales.x.getDecimalForPixel(Math.min(right, Math.max(left, evt.x)));
              onFocus?.(Math.round(f * (count - 1)));       // snap to the closest data point
              chart.draw();                                 // move the line right now (no waiting for a reactive update)
            },
            onClick(evt, _els, chart) {
              const marker = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true)
                .find((e) => e.datasetIndex === 1 && markers.has(e.index));
              if (marker) onPick?.(markers.get(marker.index));
            },
            plugins: { hwCursor: { startMs: start?.getTime(), step, count },
              legend: { display: false }, tooltip: { ...tooltip(t), callbacks: {
              title: (items) => {
                const [item] = items;
                if (item.datasetIndex === 1) return `Shift ${markers.get(item.dataIndex).device}`;
                return byIndex.get(item.dataIndex)?.title ?? when(item.dataIndex);
              },
              label: (item) => {
                if (item.datasetIndex === 1) {
                  const sh = markers.get(item.dataIndex);
                  return [`Run at ${at(sh.ideal)} instead of ${at(sh.usual)}`,
                          `Saves ≈ ${HW.fmt.money(sh.saving)} · tap to schedule`];
                }
                const h = byIndex.get(item.dataIndex);
                const lines = h ? [h.detail, ...(h.explain || []).flatMap((l) => wrap(l))]
                  : [`${item.parsed.y.toFixed(2)} kWh`];
                if (prices) lines.push(`Price: ${HW.fmt.money(prices[item.dataIndex])}/kWh`);
                return lines;
              },
            } } },
          }),
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

    /**
     * Solar: the year per month – her consumption split into what her PV share covers (accent) and what still comes
     * from the grid (grey), with the PV production as a line. `months` = pv_simulation.json monthly rows.
     */
    solarMonthly(months, { compact = false } = {}) {
      const t = theme();
      const sun = '#ffd166';
      const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const kwh = (v) => `${Math.round(v)} kWh`;
      return {
        id: `solar-monthly-${compact}`,
        config: {
          type: 'bar',
          data: { labels: names, datasets: [
            { label: 'From your PV', data: months.map((m) => m.used), backgroundColor: t.accent, stack: 'use',
              borderRadius: 3, barPercentage: .72, categoryPercentage: .9, order: 2 },
            { label: 'From the grid', data: months.map((m) => m.grid), backgroundColor: t.bar, stack: 'use',
              borderRadius: 3, barPercentage: .72, categoryPercentage: .9, order: 2 },
            { label: 'PV production', data: months.map((m) => m.production), type: 'line', borderColor: sun,
              borderWidth: 2.5, borderDash: [5, 5], pointRadius: 0, pointHoverRadius: 5, pointHoverBackgroundColor: sun,
              cubicInterpolationMode: 'monotone', order: 1 },
          ] },
          options: base(t, {
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 6 } },
            scales: {
              x: { stacked: true, display: !compact, grid: { display: false }, border: { display: false },
                   ticks: { color: token('--muted'), font: { size: 11 }, maxRotation: 0, autoSkip: false,
                            callback: (_v, i) => names[i][0] } },
              y: { stacked: true, display: !compact, beginAtZero: true, grid: { color: t.line, drawTicks: false },
                   border: { display: false }, ticks: { color: token('--muted'), font: { size: 11 }, padding: 6, maxTicksLimit: 4 } },
            },
            plugins: { legend: { display: false }, tooltip: { ...tooltip(t), callbacks: {
              title: (items) => names[items[0].dataIndex],
              label: (item) => `${item.dataset.label}: ${kwh(item.parsed.y)}`,
              afterBody: (items) => {
                const m = months[items[0].dataIndex];
                return m.demand ? [`Covered: ${Math.round((m.used / m.demand) * 100)} % · exported ${kwh(m.export)}`] : [];
              },
            } } },
          }),
        },
      };
    },

    /** Solar: payback years per size, A (as today, grey) next to B (with shifting, accent); the chosen size is solid. */
    solarSizes(sizes, kwp) {
      const t = theme();
      const rows = sizes.filter((r) => r.kwp > 0);
      const alpha = (c, on) => (on ? c : `${c}66`);
      const years = (v) => (v == null ? 'no payback' : `${v.toFixed(1)} years`);
      return {
        id: 'solar-sizes',
        config: {
          type: 'bar',
          data: { labels: rows.map((r) => `${r.kwp} kWp`), datasets: [
            { label: 'Currently', data: rows.map((r) => r.A.payback_years), borderRadius: 4,
              backgroundColor: rows.map((r) => alpha('#8d8a86', r.kwp === kwp)), barPercentage: .8, categoryPercentage: .7 },
            { label: 'With shifting', data: rows.map((r) => r.B.payback_years), borderRadius: 4,
              backgroundColor: rows.map((r) => alpha(t.accent, r.kwp === kwp)), barPercentage: .8, categoryPercentage: .7 },
          ] },
          options: base(t, {
            interaction: { mode: 'index', intersect: false },
            scales: {
              x: { grid: { display: false }, border: { display: false },
                   ticks: { color: token('--muted'), font: { size: 11 }, maxRotation: 0 } },
              y: { beginAtZero: true, grid: { color: t.line, drawTicks: false }, border: { display: false },
                   ticks: { color: token('--muted'), font: { size: 11 }, padding: 6, maxTicksLimit: 4, callback: (v) => `${v} y` } },
            },
            plugins: { legend: { display: false }, tooltip: { ...tooltip(t), callbacks: {
              title: (items) => `${rows[items[0].dataIndex].kwp} kWp · €${rows[items[0].dataIndex].investment.toLocaleString('en-US')}`,
              label: (item) => `${item.dataset.label}: ${years(item.parsed.y)}`,
            } } },
          }),
        },
      };
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
