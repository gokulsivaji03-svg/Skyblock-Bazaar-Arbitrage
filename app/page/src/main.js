import "./style.css";

const app = document.querySelector("#app");
const BAZAAR_API_URL = import.meta.env.VITE_BAZAAR_API_URL ?? "/api/bazaar";
const FORGE_API_URL = import.meta.env.VITE_FORGE_API_URL ?? "/api/forge";
const STATUS_API_URL = import.meta.env.VITE_STATUS_API_URL ?? "/api/status";
const HISTORY_API_URL = import.meta.env.VITE_HISTORY_API_URL ?? "/api/history";
const PLAYER_API_URL = import.meta.env.VITE_PLAYER_API_URL ?? "/api/player";
const SETTINGS_KEY = "skyblock-market-settings";
// Prices are never persisted — only UI settings are. We re-poll the live
// Hypixel data on this cadence so displayed prices stay current.
const REFRESH_INTERVAL_MS = 45000;
let refreshTimer = null;
let loadGeneration = 0;
let volRefetchTimer = null;
let usernameSaveTimer = null;

// Bazaar Flipper community perk reduces the 1.25% sale tax.
const TAX_PERKS = [
  { label: "None — 1.25%", rate: 0.0125 },
  { label: "Bazaar Flipper I — 1.125%", rate: 0.01125 },
  { label: "Bazaar Flipper II — 1.0%", rate: 0.01 },
];

if (!app) {
  throw new Error("Could not find #app");
}

/* ---------- icons ---------- */
const ICONS = {
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>`,
  sliders: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="6" x2="20" y2="6"/><circle cx="9" cy="6" r="2.4" fill="currentColor" stroke="none"/><line x1="4" y1="14" x2="20" y2="14"/><circle cx="15" cy="14" r="2.4" fill="currentColor" stroke="none"/></svg>`,
  sun: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`,
  moon: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>`,
  user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>`,
};

/* ---------- formatting ---------- */
const compactFmt = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });
const fullFmt = new Intl.NumberFormat("en-US");
const compact = (v) => compactFmt.format(Number(v) || 0);
const full = (v) => fullFmt.format(Math.round(Number(v) || 0));

// Fast, immutable, edge-cached SkyBlock item icons keyed by item id.
const ICON_BASE = "https://sky.coflnet.com/static/icon/";

function avatar(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) % 360;
  const h1 = hash;
  const h2 = (hash + 48) % 360;
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("");
  return `<span class="avatar" style="background:linear-gradient(135deg,hsl(${h1} 75% 62%),hsl(${h2} 80% 56%))">${initials}</span>`;
}

// Real item icon layered over the gradient avatar. The avatar shows instantly
// (and remains as a fallback if the icon 404s/errors, via onerror).
function itemIcon(name, id) {
  const fallback = avatar(name);
  if (!id) return fallback;
  const url = ICON_BASE + encodeURIComponent(id);
  return `<span class="icon-wrap">${fallback}<img class="item-img" src="${url}" alt="" width="28" height="28" loading="lazy" decoding="async" onerror="this.remove()"></span>`;
}

function profitPill(value) {
  const negative = Number(value) < 0;
  return `<span class="profit-pill ${negative ? "neg" : ""}" title="${full(value)} coins">${
    negative ? "-" : "+"
  }${compact(Math.abs(value))}</span>`;
}

function changeCell(value) {
  if (value == null || value === "") return mutedCell("—");
  const n = Number(value);
  const cls = n > 0 ? "chg-up" : n < 0 ? "chg-down" : "cell-muted";
  const sign = n > 0 ? "+" : "";
  return `<span class="${cls}">${sign}${n.toFixed(2)}%</span>`;
}

function priceCell(value) {
  const n = Number(value) || 0;
  return `<span class="fv-price" title="${full(n)}">${compact(n)}</span>`;
}

function mutedCell(text, title = "") {
  const label = title || text;
  return `<span class="cell-muted" title="${escapeAttr(String(label))}">${text}</span>`;
}

const escapeAttr = (s) => String(s).replace(/"/g, "&quot;");

/* ---------- mode config ---------- */
const itemCol = {
  key: "_name",
  label: "Item",
  render: (d, name, rank) =>
    `<div class="item-cell"><span class="rank">${rank}</span><button class="star ${
      state.watch.has(name) ? "on" : ""
    }" type="button" data-watch="${escapeAttr(name)}" title="Watch this item" aria-label="Watch">★</button>${itemIcon(
      name,
      d.id,
    )}<span class="item-name">${name}</span></div>`,
};

const budgetCol = {
  key: "_budgetProfit",
  label: "Total @ budget",
  num: true,
  sortable: true,
  render: (d) =>
    mutedCell(d._budgetUnits ? compact(d._budgetProfit) : "—", d._budgetUnits ? `${full(d._budgetUnits)} units affordable` : ""),
};

const MODES = {
  flip: {
    label: "Bazaar",
    defaultSort: "marketCap",
    searchPlaceholder: "Search bazaar items…",
    columns: [
      itemCol,
      { key: "marketCap", label: "Mkt Cap", num: true, sortable: true, render: (d) => priceCell(d.marketCap) },
      {
        key: "pe",
        label: "P/E",
        num: true,
        sortable: true,
        render: (d) => mutedCell(d.pe != null ? Number(d.pe).toFixed(1) : "—", "Mid price ÷ flip profit"),
      },
      { key: "price", label: "Price", num: true, sortable: true, render: (d) => priceCell(d.price) },
      { key: "change", label: "Chg", num: true, sortable: true, render: (d) => changeCell(d.change) },
      { key: "volume", label: "Vol", num: true, sortable: true, render: (d) => mutedCell(compact(d.volume), full(d.volume)) },
      { key: "instaBuy", label: "Inst Buy", num: true, sortable: true, render: (d) => priceCell(d.instaBuy) },
      { key: "instaSell", label: "Inst Sell", num: true, sortable: true, render: (d) => priceCell(d.instaSell) },
      { key: "buyOrderPrice", label: "Buy Ord", num: true, sortable: true, render: (d) => priceCell(d.buyOrderPrice) },
      { key: "sellOfferPrice", label: "Sell Ord", num: true, sortable: true, render: (d) => priceCell(d.sellOfferPrice) },
      { key: "profit", label: "Profit", num: true, sortable: true, sticky: true, render: (d) => profitPill(d.profit) },
    ],
    stats: [
      { label: "Products", value: (it) => full(it.length), sub: () => "live bazaar items" },
      { label: "Top mkt cap", value: (it) => compact(maxBy(it, "marketCap")), sub: () => "weekly × mid price" },
      { label: "Top volume", value: (it) => compact(maxBy(it, "volume")), sub: () => "units / week" },
      { label: "Avg change", value: (it) => `${avgBy(it.filter(([, d]) => d.change != null), "change").toFixed(2)}%`, sub: () => "24h mid price" },
    ],
  },
  forge: {
    label: "Forge",
    defaultSort: "profit",
    searchPlaceholder: "Search forge crafts…",
    columns: [
      itemCol,
      {
        key: "hotm_required",
        label: "HOTM",
        num: true,
        sortable: true,
        render: (d) => {
          const cols = d.collections_required && d.collections_required.length ? d.collections_required.join(", ") : d.collection_req;
          const title = cols ? "Also needs: " + cols : "Heart of the Mountain tier";
          return mutedCell(`T${d.hotm_required ?? "?"}`, title);
        },
      },
      {
        key: "forge_time_seconds",
        label: "Time",
        num: true,
        sortable: true,
        render: (d) => mutedCell(d.forge_time, `Quick Forge: ${d.forge_time_quick}`),
      },
      { key: "buy_cost", label: "Cost", num: true, sortable: true, render: (d) => priceCell(d.buy_cost) },
      { key: "profit_per_hour", label: "P/hr", num: true, sortable: true, render: (d) => priceCell(d.profit_per_hour) },
      { key: "profit", label: "Profit", num: true, sortable: true, sticky: true, render: (d) => profitPill(d.profit) },
    ],
    stats: [
      { label: "Craftable", value: (it) => full(it.length), sub: () => "profitable recipes" },
      { label: "Top profit", value: (it) => compact(maxBy(it, "profit")), sub: () => "per craft", profit: true },
      { label: "Best / hr", value: (it) => compact(maxBy(it, "profit_per_hour")), sub: () => "profit per hour", profit: true },
      { label: "Lowest HOTM", value: (it) => (it.length ? "T" + minBy(it, "hotm_required") : "—"), sub: () => "to start earning" },
    ],
  },
  auction: {
    label: "Auctions",
    wip: true,
    defaultSort: "profit",
    searchPlaceholder: "",
    columns: [],
    stats: [],
  },
};

function maxBy(items, key) {
  return items.reduce((m, [, d]) => Math.max(m, Number(d[key]) || 0), 0);
}
function minBy(items, key) {
  return items.reduce((m, [, d]) => Math.min(m, Number(d[key]) || Infinity), Infinity);
}
function avgBy(items, key) {
  if (!items.length) return 0;
  return items.reduce((s, [, d]) => s + (Number(d[key]) || 0), 0) / items.length;
}

/* ---------- state ---------- */
const state = {
  mode: "flip",
  theme: "dark",
  items: [],
  loading: true,
  error: false,
  lastUpdated: null,
  search: "",
  sort: [{ key: "profit", dir: "desc" }],
  sortUserSet: false,
  showFilters: false,
  showProfile: false,
  showWatchOnly: false,
  expanded: new Set(),
  filters: {
    minProfit: 0,
    minLiquidity: 0,
    maxHotm: 10,
    minVolume: 0,
  },
  // Personalization: tax perk, order pricing, HOTM cap, budget, looked-up player.
  profile: { taxPerk: 0, useOrders: false, hotmTier: 10, budget: 0, username: "", player: null },
  watch: new Set(),
  alerts: {},
  alertFired: {},
  status: null,
  history: new Map(),
  historyPending: new Set(),
};

function defaultSort() {
  return [{ key: mode().defaultSort, dir: "desc" }];
}

function mode() {
  return MODES[state.mode] ?? MODES.flip;
}

function taxRate() {
  return TAX_PERKS[state.profile.taxPerk]?.rate ?? 0.0125;
}

function columnsFor(key) {
  const cols = [...MODES[key].columns];
  if (state.profile.budget > 0 && (key === "flip" || key === "forge")) {
    cols.splice(cols.length - 1, 0, budgetCol);
  }
  return cols;
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (p.mode && MODES[p.mode]) state.mode = p.mode;
      if (p.theme === "light" || p.theme === "dark") state.theme = p.theme;
      state.filters.minProfit = Math.max(0, Number(p.minProfit) || 0);
      state.filters.minLiquidity = clamp(Number(p.minLiquidity) || 0, 0, 5);
      state.filters.maxHotm = clamp(Number(p.maxHotm ?? 10) || 10, 1, 10);
      state.filters.minVolume = Math.max(0, Number(p.minVolume) || 0);
      state.showFilters = Boolean(p.showFilters);
      state.showWatchOnly = Boolean(p.showWatchOnly);
      if (p.profile) {
        state.profile.taxPerk = clamp(Number(p.profile.taxPerk) || 0, 0, TAX_PERKS.length - 1);
        state.profile.useOrders = Boolean(p.profile.useOrders);
        state.profile.hotmTier = clamp(Number(p.profile.hotmTier ?? 10) || 10, 1, 10);
        state.profile.budget = Math.max(0, Number(p.profile.budget) || 0);
        state.profile.username = String(p.profile.username || "");
      }
      if (Array.isArray(p.watch)) state.watch = new Set(p.watch);
      if (p.alerts && typeof p.alerts === "object") state.alerts = p.alerts;
    }
  } catch (e) {
    console.warn("settings load failed", e);
  }
  state.sort = defaultSort();
  state.sortUserSet = false;
}

function saveSettings() {
  try {
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        mode: state.mode,
        theme: state.theme,
        minProfit: state.filters.minProfit,
        minLiquidity: state.filters.minLiquidity,
        maxHotm: state.filters.maxHotm,
        minVolume: state.filters.minVolume,
        showFilters: state.showFilters,
        showWatchOnly: state.showWatchOnly,
        profile: {
          taxPerk: state.profile.taxPerk,
          useOrders: state.profile.useOrders,
          hotmTier: state.profile.hotmTier,
          budget: state.profile.budget,
          username: state.profile.username,
        },
        watch: [...state.watch],
        alerts: state.alerts,
      }),
    );
  } catch (e) {
    console.warn("settings save failed", e);
  }
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/* ---------- shell ---------- */
function renderShell() {
  app.innerHTML = `
    <div class="shell">
      <div class="ambient" aria-hidden="true"></div>

      <header class="topbar">
        <div class="brand">
          <span class="brand-mark" aria-hidden="true">◆</span>
          <div class="brand-text">
            <div class="brand-name">Forge &amp; Flip</div>
            <div class="brand-sub">SkyBlock Market Intel</div>
          </div>
        </div>

        <nav class="mode-nav segment" id="segment" aria-label="Market mode">
          <button type="button" data-mode="flip">Bazaar</button>
          <button type="button" data-mode="forge">Forge</button>
          <button type="button" data-mode="auction" class="wip-tab">Auctions <span class="wip-badge">WIP</span></button>
        </nav>

        <div class="nav-actions">
          <span class="data-pill" id="data-pill" title="Data freshness">…</span>
          <button class="icon-btn" id="profile-btn" type="button" aria-label="Profile" aria-expanded="false">${ICONS.user}</button>
          <button class="icon-btn" id="theme-btn" type="button" aria-label="Toggle theme"></button>
          <button class="icon-btn" id="refresh-btn" type="button" aria-label="Refresh data">${ICONS.refresh}</button>
        </div>
      </header>

      <section class="profile-panel" id="profile" hidden></section>

      <main class="workspace">
        <div class="metrics is-empty" id="stats"></div>

        <section class="panel">
          <div class="toolbar">
            <div class="search">
              ${ICONS.search}
              <input id="search" type="search" autocomplete="off" />
            </div>
            <div class="toolbar-actions">
              <button class="tool-btn" id="watch-btn" type="button"><span class="star-ico">★</span><span>Watchlist</span></button>
              <button class="tool-btn" id="filter-btn" type="button">${ICONS.sliders}<span>Filters</span></button>
            </div>
            <div class="sort-summary" id="sort-summary"></div>
          </div>

          <div class="filters" id="filters" hidden></div>

          <div class="table-wrap">
            <table>
              <colgroup id="colgroup"></colgroup>
              <thead><tr id="head"></tr></thead>
              <tbody id="body"></tbody>
            </table>
          </div>

          <div class="table-foot">
            <span class="status-dot" id="status">Loading…</span>
            <span id="updated"></span>
          </div>
        </section>
      </main>

      <footer class="site-foot">
        <span>Forge &amp; Flip</span>
        <span class="foot-sep">·</span>
        <a href="https://api.hypixel.net/v2/skyblock/bazaar" target="_blank" rel="noreferrer">Hypixel Bazaar API</a>
      </footer>
    </div>
    <div class="toasts" id="toasts"></div>
  `;
}

/* ---------- renderers ---------- */
function applyTheme() {
  document.documentElement.setAttribute("data-theme", state.theme);
  const btn = document.querySelector("#theme-btn");
  if (btn) btn.innerHTML = state.theme === "dark" ? ICONS.sun : ICONS.moon;
}

function renderStats() {
  const host = document.querySelector("#stats");
  if (!host) return;
  const visible = visibleItems();
  const stats = mode().stats;
  if (!stats.length) {
    host.hidden = true;
    host.setAttribute("hidden", "");
    host.classList.add("is-empty");
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  host.removeAttribute("hidden");
  host.classList.remove("is-empty");
  host.innerHTML = stats
    .map(
      (s) => `
      <article class="metric-card" title="${escapeAttr(s.sub(visible))}">
        <span class="metric-label">${s.label}</span>
        <span class="metric-value ${s.profit ? "profit" : ""}">${state.loading ? "—" : s.value(visible)}</span>
        <span class="metric-sub">${s.sub(visible)}</span>
      </article>`,
    )
    .join("");
}

function renderProfile() {
  const host = document.querySelector("#profile");
  if (!host) return;
  host.hidden = !state.showProfile;
  const p = state.profile;
  const playerInfo = p.player
    ? `<div class="player-card">
         <strong>${p.player.username}</strong>
         <span>Lvl ${p.player.skyblock_level ?? "?"}</span>
         <span>Purse ${compact(p.player.purse || 0)}</span>
         <span>Bank ${compact(p.player.bank || 0)}</span>
         ${p.player.hotm_tier != null ? `<span>HOTM T${p.player.hotm_tier}</span>` : ""}
       </div>`
    : "";
  host.innerHTML = `
    <div class="profile-grid">
      <div class="field">
        <div class="field-top"><label for="p-user">Player lookup</label></div>
        <div class="lookup-row">
          <input id="p-user" type="text" placeholder="Minecraft username" value="${escapeAttr(p.username)}" />
          <button class="solid-btn" id="p-lookup" type="button">Look up</button>
        </div>
        <span class="hint" id="p-lookup-hint">Pulls purse, bank &amp; level from SkyCrypt (no API key).</span>
        ${playerInfo}
      </div>
      <div class="field">
        <div class="field-top"><label for="p-tax">Bazaar Flipper perk</label></div>
        <select id="p-tax">
          ${TAX_PERKS.map((t, i) => `<option value="${i}" ${i === p.taxPerk ? "selected" : ""}>${t.label}</option>`).join("")}
        </select>
        <span class="hint">Lowers the sale tax used in flip &amp; forge profit.</span>
      </div>
      <div class="field">
        <div class="field-top"><label for="p-hotm">Your HOTM tier</label><span class="field-value">Tier ${p.hotmTier}</span></div>
        <input id="p-hotm" type="range" min="1" max="10" step="1" value="${p.hotmTier}" />
        <span class="hint">Caps the Forge filter to crafts you can unlock.</span>
      </div>
      <div class="field">
        <div class="field-top"><label for="p-budget">Budget (coins)</label></div>
        <input id="p-budget" type="number" min="0" step="100000" value="${p.budget}" />
        <span class="hint">Adds a "Total @ budget" column = profit × units you can afford.</span>
      </div>
      <div class="field">
        <div class="field-top"><label class="check"><input id="p-orders" type="checkbox" ${p.useOrders ? "checked" : ""} /> Forge: price with buy/sell orders</label></div>
        <span class="hint">Off = instant buy/sell. On = patient order prices (cheaper ingredients, lower payout).</span>
      </div>
    </div>`;
}

function wireProfilePanel() {
  const host = document.querySelector("#profile");
  if (!host || host.dataset.wired) return;
  host.dataset.wired = "1";

  host.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;

    if (target.id === "p-tax") {
      state.profile.taxPerk = clamp(Number(target.value) || 0, 0, TAX_PERKS.length - 1);
      saveSettings();
      loadData();
    } else if (target.id === "p-budget") {
      state.profile.budget = Math.max(0, Number(target.value) || 0);
      applyDerived();
      saveSettings();
      renderHead();
      renderStats();
      renderBody();
      renderSortSummary();
    } else if (target.id === "p-orders") {
      state.profile.useOrders = target.checked;
      saveSettings();
      loadData();
    }
  });

  host.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;

    if (target.id === "p-hotm") {
      state.profile.hotmTier = clamp(Number(target.value) || 10, 1, 10);
      state.filters.maxHotm = state.profile.hotmTier;
      const label = host.querySelector(".field-value");
      if (label) label.textContent = `Tier ${state.profile.hotmTier}`;
      renderFilters();
      saveSettings();
      renderStats();
      renderBody();
    } else if (target.id === "p-user") {
      state.profile.username = target.value;
      clearTimeout(usernameSaveTimer);
      usernameSaveTimer = setTimeout(saveSettings, 400);
    }
  });

  host.addEventListener("click", (event) => {
    if (event.target.closest("#p-lookup")) lookupPlayer();
  });
}

async function lookupPlayer() {
  const name = (state.profile.username || "").trim();
  const hint = document.querySelector("#p-lookup-hint");
  if (!name) {
    if (hint) hint.textContent = "Enter a username first.";
    return;
  }
  if (hint) hint.textContent = "Looking up…";
  try {
    const res = await fetch(`${PLAYER_API_URL}/${encodeURIComponent(name)}`);
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || `status ${res.status}`);
    state.profile.player = json;
    if (json.hotm_tier != null) {
      state.profile.hotmTier = clamp(Number(json.hotm_tier), 1, 10);
      state.filters.maxHotm = state.profile.hotmTier;
    }
    saveSettings();
    renderProfile();
    renderFilters();
    renderStats();
    renderBody();
    if (hint) hint.textContent = "Loaded. Tip: set your budget from purse + bank.";
  } catch (e) {
    if (hint) hint.textContent = `Lookup failed: ${e.message}`;
  }
}

function renderFilters() {
  const host = document.querySelector("#filters");
  if (!host) return;
  host.hidden = !state.showFilters;
  syncFilterBtn();
  if (!state.showFilters) {
    host.innerHTML = "";
    return;
  }

  const profit = `
    <label class="filter-group">
      <span class="filter-label">Profit</span>
      <input id="f-profit" class="filter-input" type="number" min="0" step="1000" value="${state.filters.minProfit}" title="Min coin profit" />
    </label>`;

  let extra = "";
  if (state.mode === "flip") {
    extra = `
    <label class="filter-group">
      <span class="filter-label">Vol</span>
      <input id="f-vol" class="filter-input filter-input-sm" type="number" min="0" step="1000" value="${state.filters.minVolume}" title="Min weekly volume" />
    </label>
    <div class="filter-group filter-slider">
      <span class="filter-label">Liq</span>
      <input id="f-liq" type="range" min="0" max="5" step="0.5" value="${state.filters.minLiquidity}" title="0–5 liquidity rating. Higher fills faster." />
      <span class="filter-val" id="f-liq-val">${state.filters.minLiquidity.toFixed(1)}</span>
    </div>`;
  } else if (state.mode === "forge") {
    extra = `
    <div class="filter-group filter-slider">
      <span class="filter-label">HOTM</span>
      <input id="f-hotm" type="range" min="1" max="10" step="1" value="${state.filters.maxHotm}" title="Only show crafts you can unlock" />
      <span class="filter-val" id="f-hotm-val">T${state.filters.maxHotm}</span>
    </div>`;
  }

  host.innerHTML = `
    <div class="filter-bar-inner">
      ${profit}
      ${extra}
      <button type="button" class="filter-reset" id="filter-reset">Reset</button>
    </div>`;
}

function resetFilters() {
  state.filters.minProfit = 0;
  state.filters.minVolume = 0;
  state.filters.minLiquidity = 0;
  state.filters.maxHotm = state.profile.hotmTier || 10;
  renderFilters();
  saveSettings();
  if (state.mode === "flip") {
    loadData();
  } else {
    renderStats();
    renderBody();
  }
}

// One delegated listener on the persistent #filters container.
function wireFilters() {
  const host = document.querySelector("#filters");
  if (!host) return;
  const apply = (reload) => {
    saveSettings();
    renderStats();
    renderBody();
    if (reload) loadData();
  };
  host.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;

    if (target.id === "f-profit") {
      state.filters.minProfit = Math.max(0, Number(target.value) || 0);
    } else if (target.id === "f-vol") {
      const prev = state.filters.minVolume;
      const next = Math.max(0, Number(target.value) || 0);
      state.filters.minVolume = next;
      clearTimeout(volRefetchTimer);
      if (next < prev) {
        volRefetchTimer = setTimeout(() => loadData(), 300);
      }
    } else if (target.id === "f-liq") {
      state.filters.minLiquidity = clamp(Number(target.value) || 0, 0, 5);
      const label = document.querySelector("#f-liq-val");
      if (label) label.textContent = state.filters.minLiquidity.toFixed(1);
    } else if (target.id === "f-hotm") {
      state.filters.maxHotm = clamp(Number(target.value) || 10, 1, 10);
      const label = document.querySelector("#f-hotm-val");
      if (label) label.textContent = `T${state.filters.maxHotm}`;
    } else {
      return;
    }

    apply(false);
  });
  host.addEventListener("click", (event) => {
    if (event.target.closest("#filter-reset")) resetFilters();
  });
  host.addEventListener("change", (event) => {
    // min_volume is enforced server-side — refetch when the user commits a new value.
    if (event.target instanceof HTMLInputElement && event.target.id === "f-vol") {
      loadData();
    }
  });
}

function cycleSort(key, event) {
  const shift = event?.shiftKey ?? false;

  if (!state.sortUserSet) {
    state.sortUserSet = true;
    const current = state.sort.length === 1 && state.sort[0].key === key ? state.sort[0] : null;
    state.sort = [{ key, dir: current && current.dir === "desc" ? "asc" : "desc" }];
    return;
  }

  const i = state.sort.findIndex((s) => s.key === key);
  if (i < 0) {
    if (shift) {
      state.sort.unshift({ key, dir: "desc" });
    } else {
      state.sort = [{ key, dir: "desc" }];
    }
  } else if (state.sort[i].dir === "desc") {
    state.sort[i].dir = "asc";
  } else {
    state.sort.splice(i, 1);
  }

  if (state.sort.length === 0) {
    state.sort = defaultSort();
    state.sortUserSet = false;
  }
}

function renderColgroup() {
  const cg = document.querySelector("#colgroup");
  const table = document.querySelector(".table-wrap table");
  if (!cg) return;
  const cols = columnsFor(state.mode);
  if (table) {
    table.classList.toggle(
      "has-budget",
      state.profile.budget > 0 && (state.mode === "flip" || state.mode === "forge"),
    );
  }
  if (!cols.length) {
    cg.innerHTML = "";
    return;
  }
  cg.innerHTML = cols
    .map((col) => {
      if (col.key === "_name") return '<col class="col-item">';
      if (col.sticky) return '<col class="col-profit">';
      return '<col class="col-num">';
    })
    .join("");
}

function renderHead() {
  const head = document.querySelector("#head");
  if (!head) return;
  renderColgroup();
  const cols = columnsFor(state.mode);
  if (!cols.length) {
    head.innerHTML = "";
    return;
  }
  const multi = state.sort.length > 1;
  head.innerHTML = cols
    .map((col) => {
      const idx = state.sort.findIndex((s) => s.key === col.key);
      const active = idx >= 0;
      const arrow = active
        ? `<span class="arrow">${state.sort[idx].dir === "asc" ? "↑" : "↓"}</span>`
        : "";
      const prio = active && multi ? `<span class="sort-prio">${idx + 1}</span>` : "";
      const cls = [
        col.num ? "num" : "",
        col.sortable ? "sortable" : "",
        active ? "active" : "",
        col.sticky ? "sticky-col" : "",
      ]
        .filter(Boolean)
        .join(" ");
      return `<th class="${cls}" ${col.sortable ? `data-key="${col.key}"` : ""}>${col.label} ${arrow}${prio}</th>`;
    })
    .join("");

}

function wireTableSort() {
  const table = document.querySelector(".table-wrap table");
  if (!table || table.dataset.wired) return;
  table.dataset.wired = "1";

  table.querySelector("thead")?.addEventListener("click", (event) => {
    const th = event.target.closest("th.sortable");
    if (!th?.dataset.key) return;
    cycleSort(th.dataset.key, event);
    renderHead();
    renderBody();
    renderSortSummary();
  });
}

function wireSortSummary() {
  const toolbar = document.querySelector(".toolbar");
  if (!toolbar || toolbar.dataset.sortWired) return;
  toolbar.dataset.sortWired = "1";

  toolbar.addEventListener("click", (event) => {
    if (event.target.id !== "sort-clear") return;
    state.sort = defaultSort();
    state.sortUserSet = false;
    renderHead();
    renderBody();
    renderSortSummary();
  });
}

function labelForKey(key) {
  const col = columnsFor(state.mode).find((c) => c.key === key);
  return col ? col.label : key;
}

function renderSortSummary() {
  const host = document.querySelector("#sort-summary");
  if (!host) return;
  if (!state.sort.length) {
    host.innerHTML = "";
    return;
  }
  const chips = state.sort
    .map(
      (s, i) =>
        `<span class="sort-chip">${i + 1}. ${labelForKey(s.key)} ${s.dir === "asc" ? "↑" : "↓"}</span>`,
    )
    .join("");
  host.innerHTML = `<span class="sort-label">Sort:</span>${chips}<button type="button" class="sort-clear" id="sort-clear" title="Reset sort">Clear</button>`;
}

function visibleItems() {
  const q = state.search.trim().toLowerCase();
  return state.items.filter(([name, d]) => {
    if (state.showWatchOnly && !state.watch.has(name)) return false;
    if (q && !name.toLowerCase().includes(q) && !(d.id || "").toLowerCase().includes(q)) return false;
    if ((Number(d.profit) || 0) < state.filters.minProfit) return false;
    if (state.mode === "flip") {
      if ((Number(d.volume) || 0) < state.filters.minVolume) return false;
      if ((Number(d["liquidity rating"]) || 0) < state.filters.minLiquidity) return false;
    }
    if (state.mode === "forge") return (Number(d.hotm_required) || 0) <= state.filters.maxHotm;
    return true;
  });
}

function sortedItems() {
  const chain = state.sort.length ? state.sort : defaultSort();
  return [...visibleItems()].sort(([, a], [, b]) => {
    for (const { key, dir } of chain) {
      const mul = dir === "asc" ? 1 : -1;
      const av = sortValue(a, key, dir);
      const bv = sortValue(b, key, dir);
      if (av !== bv) return (av - bv) * mul;
    }
    return (Number(b.profit) || 0) - (Number(a.profit) || 0);
  });
}

function sortValue(row, key, dir) {
  const raw = row[key];
  if (raw == null || raw === "") {
    // Nullable metrics (e.g. 24h change, P/E) sort after real values.
    return dir === "asc" ? Infinity : -Infinity;
  }
  return Number(raw) || 0;
}

function skeletonRows(cols) {
  return Array.from({ length: 8 })
    .map(() => `<tr class="skeleton-row">${"<td><div class=\"skeleton\"></div></td>".repeat(cols)}</tr>`)
    .join("");
}

function renderBody() {
  const body = document.querySelector("#body");
  if (!body) return;
  const cols = columnsFor(state.mode);

  if (mode().wip) {
    body.innerHTML = `<tr><td class="wip-cell" colspan="${cols.length || 1}">
      <div class="wip-panel">
        <span class="wip-badge lg">Work in progress</span>
        <h3>Auction House flips</h3>
        <p>NBT-aware grouping, avg comp pricing, and pet-level filters are being rebuilt. Code lives in <code>wip/auction/</code> (gitignored) until ready.</p>
      </div>
    </td></tr>`;
    updateFoot(0);
    return;
  }

  if (state.loading) {
    body.innerHTML = skeletonRows(cols.length);
    return;
  }

  const rows = sortedItems();
  if (!rows.length) {
    body.innerHTML = `<tr><td class="empty" colspan="${cols.length}"><strong>No matches</strong>${
      state.showWatchOnly ? "Your watchlist is empty here." : "Try lowering the filters or clearing the search."
    }</td></tr>`;
    updateFoot(0);
    return;
  }

  body.innerHTML = rows
    .map(([name, d], i) => {
      const expandable = state.mode === "forge";
      const open = expandable && state.expanded.has(name);
      const rowCls = expandable
        ? `class="expandable${open ? " open" : ""}" data-name="${escapeAttr(name)}"`
        : "";
      const cells = cols
        .map((c) => {
          let inner = c.render(d, name, i + 1);
          if (expandable && c.key === "_name") {
            inner = `<span class="row-chevron${open ? " open" : ""}">▸</span>${inner}`;
          }
          const tdCls = [c.num ? "num" : "", c.sticky ? "sticky-col" : ""].filter(Boolean).join(" ");
          return `<td class="${tdCls}">${inner}</td>`;
        })
        .join("");
      const detail =
        open ? `<tr class="detail-row"><td colspan="${cols.length}">${detailHtml(name, d)}</td></tr>` : "";
      return `<tr ${rowCls}>${cells}</tr>${detail}`;
    })
    .join("");

  updateFoot(rows.length);
}

function detailHtml(name, d) {
  let html = '<div class="detail">';
  if (state.mode === "forge") {
    html += breakdownHtml(d);
    html += alertHtml(name, d);
  }
  html += "</div>";
  return html;
}

function alertHtml(name, d) {
  const t = state.alerts[name] ?? "";
  return `<div class="alert-ctl">
      <label>Alert when profit ≥</label>
      <input type="number" class="alert-input" data-alert="${escapeAttr(name)}" value="${t}" placeholder="target coins" />
      <span class="muted">current ${full(d.profit)}</span>
      ${state.alerts[name] != null ? `<button type="button" class="alert-clear" data-alert-clear="${escapeAttr(name)}">remove</button>` : ""}
    </div>`;
}

function breakdownHtml(d) {
  const ingredients = d.ingredients || [];
  if (!ingredients.length) return "";
  const lines = ingredients
    .map(
      (g) => `
      <div class="bd-line">
        <span class="bd-name">${itemIcon(g.name, g.id)}<span class="bd-label">${g.name}</span>${
        g.method ? `<span class="bd-method ${g.method}">${g.method}</span>` : ""
      }</span>
        <span class="bd-calc"><span class="bd-qty">${g.quantity}×</span> ${full(g.unit_cost)}</span>
        <span class="bd-total">${full(g.line_cost)}</span>
      </div>`,
    )
    .join("");
  const taxPct = (taxRate() * 100).toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return `
    <div class="breakdown">
      <div class="bd-head">Recipe cost breakdown</div>
      ${lines}
      <div class="bd-line bd-foot">
        <span class="bd-name">Total ingredient cost</span>
        <span class="bd-calc"></span>
        <span class="bd-total">${full(d.buy_cost)}</span>
      </div>
      <div class="bd-line">
        <span class="bd-name">Sell revenue (after ${taxPct}% tax)</span>
        <span class="bd-calc"></span>
        <span class="bd-total">${full(d.sell_revenue)}</span>
      </div>
      <div class="bd-line bd-profit">
        <span class="bd-name">Net profit</span>
        <span class="bd-calc"></span>
        <span class="bd-total">${full(d.profit)}</span>
      </div>
    </div>`;
}

/* ---------- price history charts ---------- */
function lineChart(points) {
  const pts = (points || []).filter((p) => p.buy_price || p.sell_price);
  if (pts.length < 2) return `<div class="chart-empty">Not enough history yet — snapshots build up over time.</div>`;
  const W = 600;
  const H = 130;
  const pad = 8;
  const xs = pts.map((p) => p.ts);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const vals = pts.flatMap((p) => [p.buy_price, p.sell_price].filter((v) => v));
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const sx = (t) => pad + (maxX === minX ? 0 : (t - minX) / (maxX - minX)) * (W - 2 * pad);
  const sy = (v) => H - pad - (maxV === minV ? 0 : (v - minV) / (maxV - minV)) * (H - 2 * pad);
  const path = (key) =>
    pts
      .filter((p) => p[key])
      .map((p, i) => `${i ? "L" : "M"}${sx(p.ts).toFixed(1)} ${sy(p[key]).toFixed(1)}`)
      .join(" ");
  return `
    <svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">
      <path d="${path("buy_price")}" class="line buy" fill="none" />
      <path d="${path("sell_price")}" class="line sell" fill="none" />
    </svg>
    <div class="chart-legend">
      <span class="lg buy">Instant buy</span>
      <span class="lg sell">Instant sell</span>
      <span class="lg range">${compact(minV)} – ${compact(maxV)}</span>
    </div>`;
}

function hydrateCharts() {
  state.expanded.forEach((name) => {
    const entry = state.items.find(([n]) => n === name);
    if (!entry) return;
    const d = entry[1];
    if (!d.id) return;
    const box = document.querySelector(`#chart-${cssEscape(d.id)}`);
    if (!box) return;
    if (state.history.has(d.id)) {
      box.innerHTML = lineChart(state.history.get(d.id));
      return;
    }
    if (state.historyPending.has(d.id)) return;
    state.historyPending.add(d.id);
    fetch(`${HISTORY_API_URL}/${encodeURIComponent(d.id)}?hours=24`)
      .then((r) => r.json())
      .then((j) => {
        state.history.set(d.id, j.points || []);
        const target = document.querySelector(`#chart-${cssEscape(d.id)}`);
        if (target) target.innerHTML = lineChart(j.points || []);
      })
      .catch(() => {
        const target = document.querySelector(`#chart-${cssEscape(d.id)}`);
        if (target) target.innerHTML = `<div class="chart-empty">Could not load history.</div>`;
      })
      .finally(() => state.historyPending.delete(d.id));
  });
}

function cssEscape(id) {
  return String(id).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

/* ---------- watchlist + alerts ---------- */
function toggleWatch(name) {
  if (state.watch.has(name)) state.watch.delete(name);
  else state.watch.add(name);
  saveSettings();
  renderStats();
  renderBody();
}

function checkAlerts() {
  Object.keys(state.alerts).forEach((name) => {
    const target = Number(state.alerts[name]);
    if (!target) return;
    const entry = state.items.find(([n]) => n === name);
    const profit = entry ? Number(entry[1].profit) || 0 : null;
    if (profit == null) return;
    if (profit >= target) {
      if (!state.alertFired[name]) {
        state.alertFired[name] = true;
        fireAlert(name, profit, target);
      }
    } else {
      state.alertFired[name] = false;
    }
  });
}

function fireAlert(name, profit, target) {
  toast(`${name}: profit ${compact(profit)} ≥ target ${compact(target)}`);
  try {
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification("Forge & Flip alert", { body: `${name} hit ${full(profit)} coins profit` });
    }
  } catch (e) {
    /* notifications are best-effort */
  }
}

function toast(msg) {
  const host = document.querySelector("#toasts");
  if (!host) return;
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  host.appendChild(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 6000);
}

/* ---------- budget ---------- */
function applyDerived() {
  const b = state.profile.budget;
  state.items.forEach(([, d]) => {
    if (b > 0) {
      const unit = state.mode === "flip" ? Number(d.buyOrderPrice) : Number(d.buy_cost);
      const units = unit > 0 ? Math.floor(b / unit) : 0;
      d._budgetUnits = units;
      d._budgetProfit = units * (Number(d.profit) || 0);
    } else {
      d._budgetUnits = 0;
      d._budgetProfit = 0;
    }
  });
}

/* ---------- data ---------- */
function buildEndpoint(key) {
  const tax = taxRate();
  const params = new URLSearchParams();
  if (key === "forge") {
    params.set("use_orders", String(state.profile.useOrders));
    params.set("tax_rate", String(tax));
    return `${FORGE_API_URL}?${params}`;
  }
  params.set("tax_rate", String(tax));
  params.set("min_volume", String(state.filters.minVolume || 0));
  return `${BAZAAR_API_URL}?${params}`;
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    if (!document.hidden) loadData();
    else scheduleRefresh();
  }, REFRESH_INTERVAL_MS);
}

async function loadStatus() {
  try {
    const res = await fetch(STATUS_API_URL);
    if (!res.ok) return;
    state.status = await res.json();
    renderDataPill();
  } catch (e) {
    /* status is non-critical */
  }
}

function renderDataPill() {
  const pill = document.querySelector("#data-pill");
  if (!pill) return;
  if (!state.status) {
    if (state.lastUpdated) {
      pill.className = "data-pill ok";
      pill.textContent = "live";
      pill.title = "Status unavailable";
    }
    return;
  }
  const c = state.status.cache || {};
  if (c.error) {
    pill.className = "data-pill err";
    pill.textContent = "data error";
    pill.title = c.error;
    return;
  }
  const age = c.age_seconds;
  const label = age == null ? "warming up" : age < 90 ? `live · ${Math.round(age)}s` : `stale · ${Math.round(age)}s`;
  pill.className = `data-pill ${age != null && age < 90 ? "ok" : "warn"}`;
  pill.textContent = label;
  pill.title = `Bazaar: ${c.product_count || 0} products`;
}

async function loadData() {
  const gen = ++loadGeneration;
  scheduleRefresh();
  loadStatus();

  if (mode().wip) {
    state.loading = false;
    state.error = false;
    state.items = [];
    document.querySelector("#refresh-btn")?.classList.remove("is-spinning");
    renderHead();
    renderStats();
    renderBody();
    updateFoot(0);
    return;
  }

  state.loading = true;
  state.error = false;
  const refreshBtn = document.querySelector("#refresh-btn");
  refreshBtn?.classList.add("is-spinning");
  renderStats();
  renderBody();
  updateFoot(0);

  try {
    const res = await fetch(buildEndpoint(state.mode));
    if (gen !== loadGeneration) return;
    if (!res.ok) throw new Error(`status ${res.status}`);
    const json = await res.json();
    if (gen !== loadGeneration) return;
    state.items = Object.entries(json);
    applyDerived();
    state.lastUpdated = new Date();
    checkAlerts();
  } catch (e) {
    if (gen !== loadGeneration) return;
    console.error("load failed", e);
    state.items = [];
    state.error = true;
  } finally {
    if (gen !== loadGeneration) return;
    state.loading = false;
    refreshBtn?.classList.remove("is-spinning");
    renderHead();
    renderStats();
    renderBody();
  }
}

function updateFoot(count) {
  const status = document.querySelector("#status");
  const updated = document.querySelector("#updated");
  if (status) {
    status.classList.toggle("err", state.error);
    status.textContent = state.error
      ? `Could not load ${state.mode} data`
      : `${count} of ${state.items.length} ${mode().label.toLowerCase()} items shown`;
  }
  if (updated && state.lastUpdated) {
    updated.textContent = `Updated ${state.lastUpdated.toLocaleTimeString()} · auto every ${
      REFRESH_INTERVAL_MS / 1000
    }s`;
  }
}

/* ---------- wiring ---------- */
function syncSegment() {
  document.querySelectorAll("#segment button").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.mode === state.mode);
    b.classList.toggle("is-wip", b.dataset.mode === "auction");
  });
}

function syncFilterBtn() {
  document.querySelector("#filter-btn")?.classList.toggle("is-active", state.showFilters);
}

function syncWatchBtn() {
  const btn = document.querySelector("#watch-btn");
  if (btn) btn.classList.toggle("is-active", state.showWatchOnly);
}

function wire() {
  document.querySelector("#theme-btn")?.addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme();
    saveSettings();
  });

  document.querySelector("#refresh-btn")?.addEventListener("click", () => loadData());

  document.querySelector("#profile-btn")?.addEventListener("click", () => {
    state.showProfile = !state.showProfile;
    document.querySelector("#profile-btn")?.setAttribute("aria-expanded", String(state.showProfile));
    renderProfile();
  });

  document.querySelectorAll("#segment button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = btn.dataset.mode;
      if (!next || next === state.mode) return;
      state.mode = next;
      state.sort = defaultSort();
      state.sortUserSet = false;
      state.expanded.clear();
      syncSegment();
      const searchInput = document.querySelector("#search");
      if (searchInput) searchInput.placeholder = mode().searchPlaceholder;
      saveSettings();
      renderFilters();
      renderHead();
      renderSortSummary();
      loadData();
    });
  });

  const searchInput = document.querySelector("#search");
  if (searchInput) {
    searchInput.placeholder = mode().searchPlaceholder;
    searchInput.addEventListener("input", (e) => {
      state.search = e.target.value;
      renderStats();
      renderBody();
    });
  }

  document.querySelector("#filter-btn")?.addEventListener("click", () => {
    state.showFilters = !state.showFilters;
    saveSettings();
    renderFilters();
  });

  document.querySelector("#watch-btn")?.addEventListener("click", () => {
    state.showWatchOnly = !state.showWatchOnly;
    syncWatchBtn();
    saveSettings();
    renderStats();
    renderBody();
  });

  wireFilters();
  wireProfilePanel();
  wireTableSort();
  wireSortSummary();

  const body = document.querySelector("#body");
  body?.addEventListener("click", (event) => {
    const star = event.target.closest("[data-watch]");
    if (star) {
      event.stopPropagation();
      toggleWatch(star.dataset.watch);
      return;
    }
    const clear = event.target.closest("[data-alert-clear]");
    if (clear) {
      delete state.alerts[clear.dataset.alertClear];
      saveSettings();
      renderBody();
      return;
    }
    if (event.target.closest(".alert-ctl")) return;
    if (state.mode !== "forge") return;
    const row = event.target.closest("tr.expandable");
    if (!row) return;
    const name = row.dataset.name;
    if (!name) return;
    if (state.expanded.has(name)) state.expanded.delete(name);
    else state.expanded.add(name);
    renderBody();
  });

  body?.addEventListener("change", (event) => {
    const input = event.target.closest("[data-alert]");
    if (!input) return;
    const name = input.dataset.alert;
    const val = Number(input.value);
    if (!val || val <= 0) {
      delete state.alerts[name];
    } else {
      state.alerts[name] = val;
      requestNotifyPermission();
    }
    state.alertFired[name] = false;
    saveSettings();
    renderBody();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden || state.loading) return;
    const age = state.lastUpdated ? Date.now() - state.lastUpdated.getTime() : Infinity;
    if (age >= REFRESH_INTERVAL_MS) loadData();
  });
}

function requestNotifyPermission() {
  try {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  } catch (e) {
    /* ignore */
  }
}

/* ---------- boot ---------- */
loadSettings();
renderShell();
applyTheme();
syncSegment();
syncWatchBtn();
wire();
renderProfile();
renderFilters();
renderHead();
renderSortSummary();
renderStats();
loadData();
