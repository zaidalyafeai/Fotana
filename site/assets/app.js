const RATIO_DENOMINATOR = {
  cards_per_100_challenges: "challenges",
  cards_per_100_tackles: "tackles",
  tackles_per_card: "tackles",
  challenges_per_card: "challenges",
  tackles_per_yellow: "tackles",
  fouls_per_card: "fouls_committed",
  cards_per_foul: "fouls_committed",
  fouls_per_challenge: "challenges",
  tackles_per_90: "minutes",
  challenges_per_90: "minutes",
  fouls_per_90: "minutes",
  cards_per_90: "minutes",
};

const METHODS = ["zscore", "modified_zscore", "iqr"];
const ENTITY_LABEL = { player: "Players", team: "Teams", match: "Team-in-match" };

let manifest = null;
let currentRows = [];
let lastContext = "";

function $(id) {
  return document.getElementById(id);
}

function median(values) {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function quantile(values, q) {
  const s = [...values].sort((a, b) => a - b);
  if (!s.length) return 0;
  const pos = (s.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  return s[base + 1] !== undefined ? s[base] + rest * (s[base + 1] - s[base]) : s[base];
}

function nameColumn(rows) {
  if (rows.length && "player" in rows[0]) return "player";
  if (rows.length && "team" in rows[0]) return "team";
  return Object.keys(rows[0] || {})[0];
}

function defaultMinDenom(level, denomCol, maxVal) {
  if (denomCol === "minutes") return Math.min(270, maxVal);
  if (level === "player") return Math.min(20, maxVal);
  return 0;
}

function detectOutliers(rows, column, options) {
  const {
    methods,
    minDenominator = 0,
    denominatorColumn = null,
    zscoreThreshold = 3,
    modifiedZscoreThreshold = 3.5,
    iqrK = 1.5,
  } = options;

  let work = rows.filter((r) => r[column] != null && !Number.isNaN(Number(r[column])));
  if (denominatorColumn && minDenominator > 0) {
    work = work.filter((r) => Number(r[denominatorColumn] || 0) >= minDenominator);
  }

  const values = work.map((r) => Number(r[column]));
  const mean = values.reduce((a, b) => a + b, 0) / (values.length || 1);
  const std = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / (values.length || 1));
  const med = median(values);
  const absDev = values.map((v) => Math.abs(v - med));
  const mad = median(absDev);
  const q1 = quantile(values, 0.25);
  const q3 = quantile(values, 0.75);
  const iqr = q3 - q1;
  const iqrLower = q1 - iqrK * iqr;
  const iqrUpper = q3 + iqrK * iqr;

  const enriched = work.map((row, i) => {
    const v = values[i];
    const flags = {};
    let count = 0;

    if (methods.includes("zscore")) {
      const z = std ? (v - mean) / std : 0;
      flags.zscore = z;
      flags.zscore_outlier = Math.abs(z) > zscoreThreshold;
      if (flags.zscore_outlier) count += 1;
    }
    if (methods.includes("modified_zscore")) {
      const mz = mad ? (0.6745 * (v - med)) / mad : 0;
      flags.modified_zscore = mz;
      flags.modified_zscore_outlier = Math.abs(mz) > modifiedZscoreThreshold;
      if (flags.modified_zscore_outlier) count += 1;
    }
    if (methods.includes("iqr")) {
      flags.iqr_outlier = v < iqrLower || v > iqrUpper;
      if (flags.iqr_outlier) count += 1;
    }

    const magnitude = mad ? Math.abs((0.6745 * (v - med)) / mad) : 0;
    return {
      ...row,
      ...flags,
      outlier_method_count: count,
      is_outlier: count > 0,
      outlier_score: magnitude * (1 + count),
    };
  });

  enriched.sort((a, b) => {
    if (a.is_outlier !== b.is_outlier) return a.is_outlier ? -1 : 1;
    return b.outlier_score - a.outlier_score;
  });

  return { rows: enriched, iqrBounds: [iqrLower, iqrUpper] };
}

function availableRatios(rows) {
  return Object.keys(RATIO_DENOMINATOR).filter((col) =>
    rows.some((r) => r[col] != null && !Number.isNaN(Number(r[col])))
  );
}

async function loadManifest() {
  const res = await fetch("data/manifest.json");
  if (!res.ok) throw new Error("Could not load data/manifest.json");
  manifest = await res.json();
}

async function loadDataset(key, level) {
  const ds = manifest.datasets.find((d) => d.key === key);
  const file = ds.levels[level];
  const res = await fetch(`data/${file}`);
  if (!res.ok) throw new Error(`Could not load data/${file}`);
  return res.json();
}

function populateControls() {
  const dsSelect = $("dataset");
  dsSelect.innerHTML = "";
  manifest.datasets.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d.key;
    opt.textContent = `${d.competition_name} ${d.season_name}`;
    dsSelect.appendChild(opt);
  });

  const ratioLabels = manifest.ratio_labels || {};
  $("attribution").textContent = manifest.attribution || "";
}

function getSelectedMethods() {
  return METHODS.filter((m) => $(`method-${m}`).checked);
}

function renderMetrics(result, ratio, ratioLabel) {
  const rows = result.rows;
  const outliers = rows.filter((r) => r.is_outlier).length;
  const med = median(rows.map((r) => Number(r[ratio])));
  $("metric-count").textContent = rows.length;
  $("metric-outliers").textContent = outliers;
  $("metric-median").textContent = Number.isFinite(med) ? med.toFixed(2) : "—";
  $("metric-iqr").textContent = Number.isFinite(result.iqrBounds[1])
    ? result.iqrBounds[1].toFixed(2)
    : "—";
  $("metric-median-label").textContent = `Median ${ratioLabel}`;
}

function renderScatter(result, ratio, nameCol) {
  const rows = result.rows;
  const denomCol = RATIO_DENOMINATOR[ratio] || "challenges";
  const xCol = rows[0] && denomCol in rows[0] ? denomCol : "challenges";
  const yCol = "cards" in (rows[0] || {}) ? "cards" : ratio;

  const normal = rows.filter((r) => !r.is_outlier);
  const outliers = rows.filter((r) => r.is_outlier);

  const traces = [
    {
      x: normal.map((r) => r[xCol]),
      y: normal.map((r) => r[yCol]),
      text: normal.map((r) => r[nameCol]),
      mode: "markers",
      type: "scatter",
      name: "Normal",
      marker: { color: "#4c78a8", size: 9, opacity: 0.75 },
      hovertemplate: `<b>%{text}</b><br>${xCol}: %{x}<br>${yCol}: %{y}<extra></extra>`,
    },
  ];

  if (outliers.length) {
    traces.push({
      x: outliers.map((r) => r[xCol]),
      y: outliers.map((r) => r[yCol]),
      text: outliers.map((r) => r[nameCol]),
      mode: "markers",
      type: "scatter",
      name: "Outlier",
      marker: { color: "#e45756", size: 12, line: { color: "#fff", width: 1 } },
      hovertemplate: `<b>%{text}</b><br>${xCol}: %{x}<br>${yCol}: %{y}<extra></extra>`,
    });
  }

  Plotly.newPlot(
    "scatter-chart",
    traces,
    {
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: "#e8eef5" },
      xaxis: { title: xCol.replace(/_/g, " "), gridcolor: "#2a3648" },
      yaxis: { title: yCol.replace(/_/g, " "), gridcolor: "#2a3648" },
      margin: { t: 20, r: 20, b: 50, l: 50 },
      legend: { orientation: "h", y: 1.12 },
    },
    { responsive: true, displayModeBar: false }
  );
}

function renderHistogram(result, ratio, ratioLabel) {
  const values = result.rows.map((r) => Number(r[ratio]));
  const [lo, hi] = result.iqrBounds;

  Plotly.newPlot(
    "hist-chart",
    [
      {
        x: values,
        type: "histogram",
        marker: { color: "#4c78a8" },
        nbinsx: 40,
      },
    ],
    {
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: "#e8eef5" },
      xaxis: { title: ratioLabel, gridcolor: "#2a3648" },
      yaxis: { title: "Count", gridcolor: "#2a3648" },
      margin: { t: 20, r: 20, b: 50, l: 50 },
      shapes: [
        { type: "line", x0: lo, x1: lo, y0: 0, y1: 1, yref: "paper", line: { dash: "dash", color: "#e45756" } },
        { type: "line", x0: hi, x1: hi, y0: 0, y1: 1, yref: "paper", line: { dash: "dash", color: "#e45756" } },
      ],
    },
    { responsive: true, displayModeBar: false }
  );
}

function renderTable(result, ratio, nameCol, onlyOutliers) {
  const cols = [
    nameCol,
    "team",
    "matches",
    "minutes",
    "tackles",
    "challenges",
    "fouls_committed",
    "yellow_cards",
    "cards",
    ratio,
    "outlier_method_count",
    "outlier_score",
    "is_outlier",
  ];
  const present = [...new Set(cols.filter((c, i) => cols.indexOf(c) === i && result.rows[0] && c in result.rows[0]))];
  const rows = onlyOutliers ? result.rows.filter((r) => r.is_outlier) : result.rows;

  const thead = $("table-head");
  thead.innerHTML = present.map((c) => `<th>${c.replace(/_/g, " ")}</th>`).join("");

  const tbody = $("table-body");
  tbody.innerHTML = rows
    .slice(0, 200)
    .map((r) => {
      const tds = present
        .map((c) => {
          let v = r[c];
          if (typeof v === "number" && !Number.isInteger(v)) v = v.toFixed(2);
          if (typeof v === "boolean") v = v ? "yes" : "no";
          return `<td>${v ?? ""}</td>`;
        })
        .join("");
      return `<tr class="${r.is_outlier ? "outlier" : ""}">${tds}</tr>`;
    })
    .join("");

  $("table-note").textContent =
    rows.length > 200 ? `Showing first 200 of ${rows.length} rows.` : `${rows.length} rows.`;
}

function downloadCsv(result, ratio, nameCol, onlyOutliers) {
  const cols = [
    nameCol,
    "team",
    "matches",
    "minutes",
    "tackles",
    "challenges",
    "fouls_committed",
    "yellow_cards",
    "cards",
    ratio,
    "outlier_method_count",
    "outlier_score",
    "is_outlier",
  ].filter((c, i, arr) => arr.indexOf(c) === i && result.rows[0] && c in result.rows[0]);

  const rows = onlyOutliers ? result.rows.filter((r) => r.is_outlier) : result.rows;
  const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [cols.join(",")].concat(
    rows.map((r) => cols.map((c) => escape(r[c])).join(","))
  );
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `outliers_${ratio}.csv`;
  a.click();
}

async function refresh() {
  const key = $("dataset").value;
  const level = $("level").value;
  const ctx = `${key}|${level}`;
  if (ctx !== lastContext) {
    $("min-denom").dataset.initialized = "";
    lastContext = ctx;
  }
  currentRows = await loadDataset(key, level);
  const ratios = availableRatios(currentRows);
  const ratioSelect = $("ratio");
  const prev = ratioSelect.value;
  ratioSelect.innerHTML = "";
  ratios.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r;
    opt.textContent = (manifest.ratio_labels || {})[r] || r;
    ratioSelect.appendChild(opt);
  });
  if (ratios.includes(prev)) ratioSelect.value = prev;
  else if (ratios.includes("cards_per_100_challenges")) ratioSelect.value = "cards_per_100_challenges";

  const ratio = ratioSelect.value;
  const denomCol = RATIO_DENOMINATOR[ratio] || null;
  const maxDenom = denomCol
    ? Math.max(...currentRows.map((r) => Number(r[denomCol] || 0)), 1)
    : 1;
  const slider = $("min-denom");
  if (!slider.dataset.initialized) {
    slider.max = String(maxDenom);
    slider.value = String(defaultMinDenom(level, denomCol, maxDenom));
    slider.dataset.initialized = "1";
    $("min-denom-label").textContent = denomCol || "volume";
  } else {
    slider.max = String(maxDenom);
  }
  $("min-denom-value").textContent = slider.value;

  const methods = getSelectedMethods();
  const result = detectOutliers(currentRows, ratio, {
    methods: methods.length ? methods : METHODS,
    minDenominator: Number(slider.value),
    denominatorColumn: denomCol,
  });

  const nameCol = nameColumn(result.rows);
  const ratioLabel = (manifest.ratio_labels || {})[ratio] || ratio;
  renderMetrics(result, ratio, ratioLabel);
  renderScatter(result, ratio, nameCol);
  renderHistogram(result, ratio, ratioLabel);
  renderTable(result, ratio, nameCol, $("only-outliers").checked);

  $("download-btn").onclick = () =>
    downloadCsv(result, ratio, nameCol, $("only-outliers").checked);
}

async function init() {
  try {
    await loadManifest();
    populateControls();
    ["dataset", "level", "ratio", "min-denom"].forEach((id) =>
      $(id).addEventListener("change", () => refresh())
    );
    ["method-zscore", "method-modified_zscore", "method-iqr", "only-outliers"].forEach((id) =>
      $(id).addEventListener("change", () => refresh())
    );
    $("min-denom").addEventListener("input", (e) => {
      $("min-denom-value").textContent = e.target.value;
      refresh();
    });
    await refresh();
  } catch (err) {
    $("load-error").hidden = false;
    $("load-error").textContent = `Failed to load site data: ${err.message}`;
  }
}

document.addEventListener("DOMContentLoaded", init);
