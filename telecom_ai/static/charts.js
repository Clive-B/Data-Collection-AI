"use strict";

window.AdinkraCharts = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const WIDTH = 960;
  const HEIGHT = 520;
  const FONT = "Inter, Segoe UI, sans-serif";
  const INK = "#10233f";
  const MUTED = "#5b6b82";
  const GRID = "#dce8ee";
  const BRAND = "#01afe4";

  function node(name, attributes = {}, text = null) {
    const element = document.createElementNS(NS, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    if (text !== null) element.textContent = text;
    return element;
  }

  function add(parent, name, attributes = {}, text = null) {
    const element = node(name, attributes, text);
    parent.appendChild(element);
    return element;
  }

  function text(parent, x, y, value, options = {}) {
    return add(parent, "text", {
      x,
      y,
      fill: options.fill || INK,
      "font-family": FONT,
      "font-size": options.size || 12,
      "font-weight": options.weight || 500,
      "text-anchor": options.anchor || "start",
      ...(options.rotate ? { transform: `rotate(${options.rotate} ${x} ${y})` } : {}),
    }, value);
  }

  function format(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "—";
    return new Intl.NumberFormat("en-GH", {
      notation: Math.abs(numeric) >= 1_000_000 ? "compact" : "standard",
      maximumFractionDigits: Math.abs(numeric) >= 1000 ? 1 : 2,
    }).format(numeric);
  }

  const frameState = new WeakMap();

  function chartData(chart, options = {}, hidden = new Set()) {
    const allSeries = (chart?.series || []).map((item, index) => ({
      name: item.name || `Series ${index + 1}`,
      colour: item.colour || ["#01afe4", "#ffcb05", "#1976d2", "#e31b23"][index % 4],
      points: (item.points || [])
        .filter((point) => Number.isFinite(Number(point.value)))
        .map((point) => ({ period: String(point.period), value: Number(point.value) }))
        .sort((left, right) => left.period.localeCompare(right.period)),
    }));
    const allPeriods = [...new Set(allSeries.flatMap((item) => item.points.map((point) => point.period)))].sort();
    const start = Math.max(0, options.viewport?.start ?? 0);
    const end = Math.min(allPeriods.length, options.viewport?.end ?? allPeriods.length);
    const periods = allPeriods.slice(start, end);
    const series = allSeries.filter((item) => !hidden.has(item.name)).map((item) => ({
      ...item,
      points: item.points.filter((point) => periods.includes(point.period)),
    }));
    const values = series.flatMap((item) => item.points.map((point) => point.value));
    return { series, allSeries, periods, allPeriods, values, title: chart?.title || "Telecom analysis", hidden };
  }

  function root(titleValue, description) {
    const svg = node("svg", {
      viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
      role: "img",
      "aria-label": description,
      xmlns: NS,
    });
    add(svg, "title", {}, titleValue);
    add(svg, "desc", {}, description);
    add(svg, "rect", { width: WIDTH, height: HEIGHT, rx: 20, fill: "#ffffff" });
    text(svg, 42, 42, titleValue, { size: 22, weight: 750 });
    return svg;
  }

  function legend(svg, data, y = 495) {
    let x = 42;
    data.allSeries.forEach((item) => {
      const isHidden = data.hidden.has(item.name);
      const group = add(svg, "g", {
        class: `chart-legend-item${isHidden ? " is-hidden" : ""}`,
        tabindex: 0, role: "button", "aria-pressed": isHidden ? "false" : "true",
        "aria-label": `${isHidden ? "Show" : "Hide"} ${item.name}`,
        "data-chart-legend": item.name,
      });
      add(group, "circle", { cx: x + 6, cy: y - 4, r: 6, fill: item.colour });
      text(group, x + 19, y, item.name, { size: 12, weight: 650, fill: isHidden ? MUTED : INK });
      x += Math.max(120, item.name.length * 8 + 45);
    });
  }

  function mark(element, item, period, value, formattedValue = format(value)) {
    Object.entries({ tabindex: 0, role: "button", "data-chart-mark": "true", "data-operator": item.name,
      "data-period": period, "data-value": value, "data-formatted-value": formattedValue,
      "aria-label": `${item.name}, ${period}, ${formattedValue}` }).forEach(([key, content]) => element.setAttribute(key, String(content)));
    add(element, "title", {}, `${item.name} · ${period}: ${formattedValue}`);
    return element;
  }

  function empty(titleValue, message = "No numeric series available") {
    const svg = root(titleValue, message);
    text(svg, WIDTH / 2, HEIGHT / 2, message, { anchor: "middle", size: 16, fill: MUTED });
    return svg;
  }

  function scaleBounds(values, zeroBaseline = true) {
    if (!values.length) return { minimum: 0, maximum: 1 };
    let minimum = Math.min(...values);
    let maximum = Math.max(...values);
    if (zeroBaseline && minimum >= 0) minimum = 0;
    const padding = (maximum - minimum) * 0.08 || Math.max(Math.abs(maximum) * 0.08, 1);
    return { minimum, maximum: maximum + padding };
  }

  function axes(svg, data, options = {}) {
    const left = 86;
    const right = 32;
    const top = 76;
    const bottom = 76;
    const plotWidth = WIDTH - left - right;
    const plotHeight = HEIGHT - top - bottom;
    const bounds = scaleBounds(data.values, options.zeroBaseline !== false);
    const x = (period) => left + data.periods.indexOf(period) * plotWidth / Math.max(1, data.periods.length - 1);
    const y = (value) => top + (bounds.maximum - value) * plotHeight / Math.max(1e-12, bounds.maximum - bounds.minimum);
    for (let index = 0; index < 5; index += 1) {
      const value = bounds.minimum + (bounds.maximum - bounds.minimum) * index / 4;
      const yPosition = y(value);
      add(svg, "line", { x1: left, y1: yPosition, x2: WIDTH - right, y2: yPosition, stroke: GRID });
      text(svg, left - 12, yPosition + 4, format(value), { anchor: "end", size: 11, fill: MUTED });
    }
    const labelStep = Math.max(1, Math.ceil(data.periods.length / 10));
    if (options.showXLabels !== false) {
      data.periods.forEach((period, index) => {
        if (index % labelStep === 0 || index === data.periods.length - 1) {
          text(svg, x(period), HEIGHT - bottom + 28, period, { anchor: "middle", size: 11, fill: MUTED });
        }
      });
    }
    return { left, right, top, bottom, plotWidth, plotHeight, x, y, bounds };
  }

  function lineOrArea(data, area = false) {
    if (!data.values.length) return empty(data.title);
    const svg = root(data.title, `${area ? "Area" : "Line"} chart of ${data.title}`);
    const layout = axes(svg, data);
    data.series.forEach((item) => {
      const coordinates = item.points.map((point) => `${layout.x(point.period)},${layout.y(point.value)}`);
      if (!coordinates.length) return;
      if (area) {
        const baseline = layout.y(layout.bounds.minimum);
        add(svg, "polygon", {
          points: `${layout.x(item.points[0].period)},${baseline} ${coordinates.join(" ")} ${layout.x(item.points[item.points.length - 1].period)},${baseline}`,
          fill: item.colour,
          opacity: 0.16,
        });
      }
      add(svg, "polyline", {
        points: coordinates.join(" "),
        fill: "none",
        stroke: item.colour,
        "stroke-width": 4,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      });
      item.points.forEach((point) => {
        const marker = add(svg, "circle", {
          cx: layout.x(point.period), cy: layout.y(point.value), r: 4.5,
          fill: "#ffffff", stroke: item.colour, "stroke-width": 3,
        });
        mark(marker, item, point.period, point.value);
      });
    });
    legend(svg, data);
    return svg;
  }

  function bar(data) {
    if (!data.values.length) return empty(data.title);
    const periods = data.periods.slice(-12);
    const displayed = {
      ...data,
      periods,
      values: data.series.flatMap((item) => item.points.filter((point) => periods.includes(point.period)).map((point) => point.value)),
    };
    const svg = root(data.title, `Grouped bar chart of ${data.title}, latest ${periods.length} periods`);
    const layout = axes(svg, displayed, { showXLabels: false });
    const groupWidth = layout.plotWidth / Math.max(1, periods.length);
    const barWidth = Math.max(3, groupWidth * 0.72 / Math.max(1, data.series.length));
    periods.forEach((period, periodIndex) => {
      const groupStart = layout.left + periodIndex * groupWidth + groupWidth * 0.14;
      text(svg, layout.left + periodIndex * groupWidth + groupWidth / 2, HEIGHT - layout.bottom + 28, period, { anchor: "middle", size: 11, fill: MUTED });
      data.series.forEach((item, seriesIndex) => {
        const point = item.points.find((candidate) => candidate.period === period);
        if (!point) return;
        const yPosition = layout.y(point.value);
        const baseline = layout.y(layout.bounds.minimum);
        const rectangle = add(svg, "rect", {
          x: groupStart + seriesIndex * barWidth,
          y: yPosition,
          width: Math.max(2, barWidth - 2),
          height: Math.max(1, baseline - yPosition),
          rx: 3,
          fill: item.colour,
        });
        mark(rectangle, item, period, point.value);
      });
    });
    legend(svg, data);
    return svg;
  }

  function radar(data) {
    if (!data.values.length) return empty(data.title);
    const periods = data.periods.slice(-8);
    const svg = root(data.title, `Radar chart of ${data.title}, latest ${periods.length} periods`);
    const centerX = 390;
    const centerY = 280;
    const radius = 160;
    const maximum = Math.max(...data.series.flatMap((item) => item.points.filter((point) => periods.includes(point.period)).map((point) => point.value)), 1);
    for (let ring = 1; ring <= 5; ring += 1) {
      const points = periods.map((_, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / periods.length;
        return `${centerX + Math.cos(angle) * radius * ring / 5},${centerY + Math.sin(angle) * radius * ring / 5}`;
      });
      add(svg, "polygon", { points: points.join(" "), fill: "none", stroke: GRID });
    }
    periods.forEach((period, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / periods.length;
      add(svg, "line", { x1: centerX, y1: centerY, x2: centerX + Math.cos(angle) * radius, y2: centerY + Math.sin(angle) * radius, stroke: GRID });
      text(svg, centerX + Math.cos(angle) * (radius + 25), centerY + Math.sin(angle) * (radius + 25) + 4, period, {
        anchor: Math.cos(angle) > 0.2 ? "start" : Math.cos(angle) < -0.2 ? "end" : "middle",
        size: 11,
        fill: MUTED,
      });
    });
    data.series.forEach((item) => {
      const pointMap = new Map(item.points.map((point) => [point.period, point.value]));
      const coordinates = periods.map((period, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / periods.length;
        const scaled = (pointMap.get(period) || 0) / maximum * radius;
        return [centerX + Math.cos(angle) * scaled, centerY + Math.sin(angle) * scaled];
      });
      add(svg, "polygon", { points: coordinates.map((point) => point.join(",")).join(" "), fill: item.colour, opacity: 0.14, stroke: item.colour, "stroke-width": 3 });
      coordinates.forEach(([x, y], index) => {
        const marker = add(svg, "circle", { cx: x, cy: y, r: 4, fill: item.colour });
        mark(marker, item, periods[index], pointMap.get(periods[index]) || 0);
      });
    });
    legend(svg, data, 500);
    text(svg, 705, 170, "Scale", { size: 12, weight: 750, fill: MUTED });
    text(svg, 705, 202, `0 – ${format(maximum)}`, { size: 23, weight: 750 });
    text(svg, 705, 230, `Latest ${periods.length} periods`, { size: 12, fill: MUTED });
    return svg;
  }

  function heatmap(data) {
    if (!data.values.length) return empty(data.title);
    const periods = data.periods.slice(-12);
    const svg = root(data.title, `Heatmap of ${data.title}, latest ${periods.length} periods`);
    const left = 150;
    const top = 120;
    const cellWidth = Math.min(70, (WIDTH - left - 45) / Math.max(1, periods.length));
    const cellHeight = Math.min(62, 260 / Math.max(1, data.series.length));
    const minimum = Math.min(...data.values);
    const maximum = Math.max(...data.values);
    periods.forEach((period, index) => text(svg, left + index * cellWidth + cellWidth / 2, top - 15, period, { anchor: "middle", size: 10, fill: MUTED, rotate: -35 }));
    data.series.forEach((item, rowIndex) => {
      text(svg, left - 14, top + rowIndex * cellHeight + cellHeight / 2 + 4, item.name, { anchor: "end", size: 12, weight: 700 });
      const points = new Map(item.points.map((point) => [point.period, point.value]));
      periods.forEach((period, columnIndex) => {
        const value = points.get(period);
        const ratio = value === undefined ? 0 : (value - minimum) / Math.max(1e-12, maximum - minimum);
        const rectangle = add(svg, "rect", {
          x: left + columnIndex * cellWidth + 2,
          y: top + rowIndex * cellHeight + 2,
          width: cellWidth - 4,
          height: cellHeight - 4,
          rx: 8,
          fill: value === undefined ? "#eff4f7" : item.colour,
          opacity: value === undefined ? 1 : 0.22 + ratio * 0.78,
          stroke: "#dce8ee",
        });
        if (value !== undefined) mark(rectangle, item, period, value);
        if (value !== undefined && cellWidth >= 58) {
          text(svg, left + columnIndex * cellWidth + cellWidth / 2, top + rowIndex * cellHeight + cellHeight / 2 + 4, format(value), {
            anchor: "middle", size: 10, weight: 700, fill: ratio > 0.58 ? "#ffffff" : INK,
          });
        }
      });
    });
    text(svg, left, top + data.series.length * cellHeight + 38, "Lighter → lower · darker → higher within the displayed data", { size: 11, fill: MUTED });
    legend(svg, data, 500);
    return svg;
  }

  // Keep the full operator legend available so a hidden series can always be restored.
  // Heatmap labels remain uncluttered while this control stays keyboard accessible.

  function polar(cx, cy, radius, angle) {
    const radians = (angle - 90) * Math.PI / 180;
    return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
  }

  function arcPath(cx, cy, radius, startAngle, endAngle) {
    const start = polar(cx, cy, radius, endAngle);
    const end = polar(cx, cy, radius, startAngle);
    return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${endAngle - startAngle <= 180 ? 0 : 1} 0 ${end.x} ${end.y}`;
  }

  function gauge(data) {
    if (!data.values.length) return empty(data.title);
    const latest = data.series.map((item) => ({ ...item, point: item.points[item.points.length - 1] })).filter((item) => item.point);
    const latestMaximum = Math.max(...latest.map((item) => item.point.value), 1);
    const isPercentage = latest.every((item) => item.point.value >= 0 && item.point.value <= 100) && /rate|percent|penetration|share|%/i.test(data.title);
    const scaleMaximum = isPercentage ? 100 : latestMaximum;
    const svg = root(data.title, `Gauge view of the latest ${data.title} values`);
    const cardWidth = 860 / Math.max(1, latest.length);
    latest.forEach((item, index) => {
      const cx = 50 + cardWidth * index + cardWidth / 2;
      const cy = 285;
      const radius = Math.min(115, cardWidth * 0.35);
      const ratio = Math.max(0, Math.min(1, item.point.value / scaleMaximum));
      add(svg, "path", { d: arcPath(cx, cy, radius, -120, 120), fill: "none", stroke: "#e7eef3", "stroke-width": 22, "stroke-linecap": "round" });
      const arc = add(svg, "path", { d: arcPath(cx, cy, radius, -120, -120 + 240 * ratio), fill: "none", stroke: item.colour, "stroke-width": 22, "stroke-linecap": "round" });
      mark(arc, item, item.point.period, item.point.value);
      text(svg, cx, cy - 8, format(item.point.value), { anchor: "middle", size: latest.length > 2 ? 25 : 34, weight: 800 });
      text(svg, cx, cy + 22, item.point.period, { anchor: "middle", size: 12, fill: MUTED });
      text(svg, cx, cy + radius + 52, item.name, { anchor: "middle", size: 14, weight: 750 });
    });
    text(svg, WIDTH / 2, 475, isPercentage ? "Scale: 0–100%" : "Relative scale: each latest value compared with the highest latest operator value", { anchor: "middle", size: 11, fill: MUTED });
    legend(svg, data, 78);
    return svg;
  }

  function donut(data) {
    if (!data.values.length) return empty(data.title);
    const commonPeriods = data.periods.filter((period) => data.series.every((item) => item.points.some((point) => point.period === period)));
    const period = commonPeriods[commonPeriods.length - 1] || data.periods[data.periods.length - 1];
    const slices = data.series.map((item) => ({ ...item, point: item.points.find((point) => point.period === period) })).filter((item) => item.point && item.point.value >= 0);
    const total = slices.reduce((sum, item) => sum + item.point.value, 0);
    if (!total) return empty(data.title, "No positive values are available for a share chart");
    const svg = root(data.title, `Donut share chart of ${data.title} for ${period}`);
    const cx = 300;
    const cy = 285;
    const radius = 138;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;
    add(svg, "circle", { cx, cy, r: radius, fill: "none", stroke: "#edf2f6", "stroke-width": 34 });
    slices.forEach((item) => {
      const share = item.point.value / total;
      const circle = add(svg, "circle", {
        cx, cy, r: radius, fill: "none", stroke: item.colour, "stroke-width": 34,
        "stroke-dasharray": `${share * circumference} ${circumference}`,
        "stroke-dashoffset": -offset,
        transform: `rotate(-90 ${cx} ${cy})`,
      });
      mark(circle, item, period, item.point.value, `${format(item.point.value)} (${(share * 100).toFixed(1)}%)`);
      offset += share * circumference;
    });
    text(svg, cx, cy - 4, format(total), { anchor: "middle", size: 34, weight: 800 });
    text(svg, cx, cy + 24, `Total · ${period}`, { anchor: "middle", size: 12, fill: MUTED });
    text(svg, 565, 150, "Operator share", { size: 13, weight: 750, fill: MUTED });
    slices.forEach((item, index) => {
      const y = 195 + index * 72;
      const share = item.point.value / total;
      add(svg, "circle", { cx: 577, cy: y - 5, r: 7, fill: item.colour });
      text(svg, 598, y, item.name, { size: 14, weight: 750 });
      text(svg, 865, y, `${(share * 100).toFixed(1)}%`, { anchor: "end", size: 18, weight: 800 });
      text(svg, 598, y + 23, format(item.point.value), { size: 12, fill: MUTED });
    });
    legend(svg, data, 500);
    return svg;
  }

  const renderers = {
    line: (data) => lineOrArea(data, false),
    bar,
    area: (data) => lineOrArea(data, true),
    radar,
    heatmap,
    gauge,
    donut,
  };

  const captions = {
    line: "Trend view across all available reporting periods.",
    bar: "Grouped comparison using the latest 12 reporting periods.",
    area: "Filled trend view; values use the same zero-based scale as the line chart.",
    radar: "Normalized radial comparison using the latest eight reporting periods.",
    heatmap: "Colour intensity comparison using the latest 12 reporting periods.",
    gauge: "Latest-value gauge; non-percentage metrics use a clearly labelled relative scale.",
    donut: "Operator share calculated from the latest reporting period common to the displayed series.",
  };

  function matchingEvidence(evidence, operator, period) {
    return (evidence || []).find((item) => item.operator === operator && String(item.period) === String(period));
  }

  function wireInteractions(frame, svg, chart, type, options, state) {
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    tooltip.hidden = true;
    tooltip.setAttribute("role", "tooltip");
    frame.appendChild(tooltip);

    function showTooltip(target, event) {
      const evidence = matchingEvidence(options.evidence, target.dataset.operator, target.dataset.period);
      tooltip.replaceChildren();
      const heading = document.createElement("strong");
      heading.textContent = target.dataset.operator;
      const value = document.createElement("span");
      value.textContent = `${target.dataset.period} · ${target.dataset.formattedValue}`;
      tooltip.append(heading, value);
      if (evidence?.source) {
        const source = document.createElement("small");
        source.textContent = evidence.source;
        tooltip.appendChild(source);
      }
      const bounds = frame.getBoundingClientRect();
      const targetBounds = target.getBoundingClientRect();
      const x = event?.clientX ? event.clientX - bounds.left : targetBounds.left - bounds.left;
      const y = event?.clientY ? event.clientY - bounds.top : targetBounds.top - bounds.top;
      tooltip.style.left = `${Math.max(8, Math.min(Math.max(8, bounds.width - 250), x + 12))}px`;
      tooltip.style.top = `${Math.max(8, y - 18)}px`;
      tooltip.hidden = false;
    }

    svg.querySelectorAll("[data-chart-mark]").forEach((target) => {
      target.addEventListener("pointerenter", (event) => showTooltip(target, event));
      target.addEventListener("pointermove", (event) => showTooltip(target, event));
      target.addEventListener("pointerleave", () => { tooltip.hidden = true; });
      target.addEventListener("focus", () => showTooltip(target));
      target.addEventListener("blur", () => { tooltip.hidden = true; });
      const select = () => options.onSelect?.({ operator: target.dataset.operator, period: target.dataset.period,
        value: Number(target.dataset.value), formattedValue: target.dataset.formattedValue });
      target.addEventListener("click", select);
      target.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); }
      });
    });

    svg.querySelectorAll("[data-chart-legend]").forEach((target) => {
      const toggle = () => {
        const operator = target.dataset.chartLegend;
        if (state.hidden.has(operator)) state.hidden.delete(operator);
        else if (state.hidden.size < Math.max(0, (chart.series || []).length - 1)) state.hidden.add(operator);
        render(frame, chart, type, options);
      };
      target.addEventListener("click", toggle);
      target.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
      });
    });
  }

  function render(frame, chart, type = "line", options = {}) {
    const state = frameState.get(frame) || { hidden: new Set() };
    if (state.chart !== chart) {
      state.hidden.clear();
      state.chart = chart;
    }
    frameState.set(frame, state);
    const validNames = new Set((chart?.series || []).map((item) => item.name));
    state.hidden.forEach((name) => { if (!validNames.has(name)) state.hidden.delete(name); });
    const data = chartData(chart, options, state.hidden);
    const renderer = renderers[type] || renderers.line;
    const svg = renderer(data);
    svg.dataset.chartType = type;
    frame.replaceChildren(svg);
    wireInteractions(frame, svg, chart, type, options, state);
    return captions[type] || captions.line;
  }

  function download(frame, titleValue, type) {
    const svg = frame.querySelector("svg");
    if (!svg) return false;
    const content = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([content], { type: "image/svg+xml;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${String(titleValue || "adinkra-chart").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}-${type}.svg`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    return true;
  }

  return { render, download };
})();
