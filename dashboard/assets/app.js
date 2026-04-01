const DATA_PATHS = {
  tweets: "../memory/tweet_log.jsonl",
  strategies: "../memory/strategy_log.jsonl",
  experiments: "../data/experiments.jsonl",
};

export async function loadJSONL(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  const text = await response.text();
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

export async function loadDataset() {
  const [tweets, strategies, experiments] = await Promise.all([
    safeLoadJSONL(DATA_PATHS.tweets),
    safeLoadJSONL(DATA_PATHS.strategies),
    safeLoadJSONL(DATA_PATHS.experiments),
  ]);

  tweets.sort((a, b) => parseDate(b.posted_at) - parseDate(a.posted_at));
  strategies.sort((a, b) => parseDate(a.date || a.created_at || "") - parseDate(b.date || b.created_at || ""));
  experiments.sort((a, b) => parseDate(b.posted_at) - parseDate(a.posted_at));

  return {
    tweets,
    strategies,
    experiments,
    matureTweets: tweets.filter(
      (tweet) => tweet.metrics_maturity === "mature" && typeof tweet.engagement_score === "number"
    ),
    latestStrategy: strategies.at(-1) || null,
  };
}

async function safeLoadJSONL(path) {
  try {
    return await loadJSONL(path);
  } catch {
    return [];
  }
}

export function parseDate(value) {
  if (!value) {
    return new Date(0);
  }
  return new Date(value);
}

export function formatDate(value, options = {}) {
  if (!value) {
    return "N/A";
  }
  const date = parseDate(value);
  if (Number.isNaN(date.getTime())) {
    return "N/A";
  }
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: options.dateStyle || "medium",
    timeStyle: options.timeStyle,
  }).format(date);
}

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(Number(value));
}

export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  return `${Number(value).toFixed(1)}%`;
}

export function average(values) {
  const filtered = values
    .map((value) => Number(value))
    .filter((value) => !Number.isNaN(value));
  if (!filtered.length) {
    return null;
  }
  return filtered.reduce((sum, value) => sum + value, 0) / filtered.length;
}

export function sum(values) {
  return values
    .map((value) => Number(value))
    .filter((value) => !Number.isNaN(value))
    .reduce((total, value) => total + value, 0);
}

export function groupBy(list, keyFn) {
  return list.reduce((acc, item) => {
    const key = keyFn(item);
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(item);
    return acc;
  }, {});
}

export function truncate(text, maxLength = 100) {
  if (!text) {
    return "";
  }
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

export function deltaClass(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "neutral";
  }
  if (value > 0) {
    return "positive";
  }
  if (value < 0) {
    return "negative";
  }
  return "neutral";
}

export function deltaText(value, suffix = "%") {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "No comparison data";
  }
  const sign = value > 0 ? "+" : value < 0 ? "-" : "=";
  const abs = Math.abs(value).toFixed(1);
  return `${sign} ${abs}${suffix}`;
}

export function comparePeriods(items, selector, days = 7, useAverage = false) {
  const now = Date.now();
  const currentStart = now - days * 86400000;
  const previousStart = now - days * 2 * 86400000;

  const current = [];
  const previous = [];

  for (const item of items) {
    const date = parseDate(item.posted_at || item.date || item.created_at).getTime();
    const value = selector(item);
    if (date >= currentStart) {
      current.push(value);
    } else if (date >= previousStart) {
      previous.push(value);
    }
  }

  const currentValue = useAverage ? average(current) : current.length;
  const previousValue = useAverage ? average(previous) : previous.length;

  if (currentValue === null || previousValue === null || previousValue === 0) {
    return null;
  }

  return ((currentValue - previousValue) / Math.abs(previousValue)) * 100;
}

export function confidenceBadge(level) {
  if (!level) {
    return "muted";
  }
  const normalized = String(level).toLowerCase();
  if (normalized === "high") {
    return "success";
  }
  if (normalized === "medium") {
    return "accent";
  }
  if (normalized === "low") {
    return "warning";
  }
  return "muted";
}

export function maturityBadge(level) {
  if (level === "mature") {
    return "success";
  }
  if (level === "settling") {
    return "accent";
  }
  if (level === "fresh") {
    return "warning";
  }
  return "muted";
}

export function metricValue(tweet, key) {
  const value = tweet?.metrics?.[key];
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

export function renderEmpty(target, message = "No data yet. The bot will populate this after its first run.") {
  target.innerHTML = `<div class="empty-state">${message}</div>`;
}

export function buildPill(label, variant = "accent", extraClasses = "") {
  return `<span class="pill ${variant} ${extraClasses}">${escapeHtml(label)}</span>`;
}

export function initials(text = "") {
  return text
    .split(/[\s_]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("") || "XB";
}

export function chartDefaults() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#12121a",
        borderColor: "rgba(124, 58, 237, 0.35)",
        borderWidth: 1,
        titleFont: { family: "DM Mono" },
        bodyFont: { family: "DM Mono" },
      },
    },
    scales: {
      x: {
        grid: { color: "rgba(30, 30, 46, 0.45)", drawBorder: false },
        ticks: { color: "#6b6b8a", font: { family: "DM Mono", size: 11 } },
      },
      y: {
        grid: { color: "rgba(30, 30, 46, 0.45)", drawBorder: false },
        ticks: { color: "#6b6b8a", font: { family: "DM Mono", size: 11 } },
      },
    },
  };
}

export function createChart(canvas, config) {
  if (!window.Chart || !canvas) {
    return null;
  }
  return new window.Chart(canvas, config);
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function mountActiveNav(page) {
  document.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.dataset.nav === page) {
      link.classList.add("active");
    }
  });
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

export function latestRunSnapshot(dataset) {
  const latestTweet = dataset.tweets[0] || null;
  const latestExperiment = dataset.experiments[0] || null;
  const latestStrategy = dataset.latestStrategy;
  return {
    latestTweet,
    latestExperiment,
    latestStrategy,
  };
}

export function uniqueValues(items, key) {
  return [...new Set(items.map((item) => item[key]).filter(Boolean))].sort();
}

export function dayBucket(items, valueFn) {
  const groups = {};
  for (const item of items) {
    const day = formatDate(item.posted_at || item.date || item.created_at, { dateStyle: "short" });
    if (!groups[day]) {
      groups[day] = [];
    }
    groups[day].push(valueFn(item));
  }
  return groups;
}

export function scoreColor(score, min, max) {
  if (score === null || score === undefined || Number.isNaN(Number(score))) {
    return "rgba(255,255,255,0.02)";
  }
  if (max <= min) {
    return "rgba(124, 58, 237, 0.18)";
  }
  const ratio = (score - min) / (max - min);
  const alpha = 0.12 + ratio * 0.5;
  return `rgba(124, 58, 237, ${alpha.toFixed(3)})`;
}
