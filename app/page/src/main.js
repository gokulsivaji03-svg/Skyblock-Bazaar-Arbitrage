import "./style.css";

const app = document.querySelector("#app");
const API_URL = import.meta.env.VITE_FLIPS_API_URL ?? "/api/flip";
const SETTINGS_STORAGE_KEY = "bazaar-arb-settings";

if (!app) {
  throw new Error("Could not find #app");
}

const state = {
  items: [],
  sortKey: "profit",
  sortDirection: "desc",
  filters: {
    minProfit: 0,
    minLiquidityRating: 0,
  },
  isSettingsOpen: false,
};

app.innerHTML = `
  <main class="dashboard-shell">
    <section class="hero-panel">
      <div class="hero-actions">
        <div>
          <p class="eyebrow">SkyBlock Bazaar</p>
          <h1>Arbitrage Board</h1>
        </div>
        <button
          id="settings-toggle"
          class="settings-toggle"
          type="button"
          aria-controls="settings-panel"
          aria-expanded="false"
        >
          Settings
        </button>
      </div>
      <p class="hero-copy">
        Track profitable flips, adjust live filters, and sort by profit or liquidity rating without leaving the page.
      </p>
      <div class="status-row">
        <span class="status-pill" id="load-status">Loading data...</span>
      </div>
      <section id="settings-panel" class="settings-panel" hidden>
        <div class="settings-grid">
          <label class="setting-card" for="min-profit">
            <span class="setting-label">Minimum profit</span>
            <input id="min-profit" type="number" min="0" step="100" value="0" />
            <span class="setting-help">Only show flips at or above this coin profit.</span>
          </label>
          <label class="setting-card" for="min-liquidity">
            <span class="setting-label">Minimum liquidity</span>
            <input id="min-liquidity" type="range" min="0" max="5" step="0.5" value="0" />
            <span class="setting-help">
              <strong id="min-liquidity-value">0.0 / 5</strong>
              using the backend liquidity rating
            </span>
          </label>
        </div>
      </section>
    </section>

    <section class="table-panel">
      <table id="data-table">
        <thead>
          <tr>
            <th data-sort-key="profit" scope="col">Profit</th>
            <th scope="col">Item</th>
            <th data-sort-key="liquidity rating" scope="col">Liquidity / 5</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </section>
  </main>
`;

const tableBody = document.querySelector("#data-table tbody");
const loadStatus = document.querySelector("#load-status");
const sortableHeaders = document.querySelectorAll("th[data-sort-key]");
const settingsToggle = document.querySelector("#settings-toggle");
const settingsPanel = document.querySelector("#settings-panel");
const minProfitInput = document.querySelector("#min-profit");
const minLiquidityInput = document.querySelector("#min-liquidity");
const minLiquidityValue = document.querySelector("#min-liquidity-value");

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value) || 0);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function loadStoredSettings() {
  try {
    const rawValue = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!rawValue) {
      return;
    }

    const parsed = JSON.parse(rawValue);
    state.filters.minProfit = Math.max(0, Number(parsed?.minProfit) || 0);
    state.filters.minLiquidityRating = clamp(
      Number(parsed?.minLiquidityRating) || 0,
      0,
      5,
    );
    state.isSettingsOpen = Boolean(parsed?.isSettingsOpen);
  } catch (error) {
    console.warn("Could not load saved settings:", error);
  }
}

function saveSettings() {
  try {
    localStorage.setItem(
      SETTINGS_STORAGE_KEY,
      JSON.stringify({
        minProfit: state.filters.minProfit,
        minLiquidityRating: state.filters.minLiquidityRating,
        isSettingsOpen: state.isSettingsOpen,
      }),
    );
  } catch (error) {
    console.warn("Could not save settings:", error);
  }
}

function syncSettingsPanel() {
  if (!settingsPanel || !settingsToggle) {
    return;
  }

  if (state.isSettingsOpen) {
    settingsPanel.removeAttribute("hidden");
  } else {
    settingsPanel.setAttribute("hidden", "");
  }

  settingsToggle.setAttribute("aria-expanded", String(state.isSettingsOpen));
}

function getSortValue(itemData, sortKey) {
  return Number(itemData?.[sortKey] ?? 0);
}

function getFilteredItems() {
  return state.items.filter(([, itemData]) => {
    const profit = Number(itemData?.profit ?? 0);
    const liquidityRating = Number(itemData?.["liquidity rating"] ?? 0);

    return (
      profit >= state.filters.minProfit &&
      liquidityRating >= state.filters.minLiquidityRating
    );
  });
}

function updateSortHeaders() {
  sortableHeaders.forEach((header) => {
    const sortKey = header.dataset.sortKey;
    const isActive = sortKey === state.sortKey;
    const arrow = !isActive ? "" : state.sortDirection === "asc" ? " ↑" : " ↓";

    header.dataset.label ||= header.textContent.trim();
    header.classList.toggle("is-active", isActive);
    header.classList.add("is-sortable");
    header.setAttribute(
      "aria-sort",
      isActive ? (state.sortDirection === "asc" ? "ascending" : "descending") : "none",
    );
    header.textContent = `${header.dataset.label}${arrow}`;
  });
}

function updateFilterSummary(filteredCount) {
  if (!loadStatus) {
    return;
  }

  const filterBits = [
    `min profit ${formatNumber(state.filters.minProfit)}`,
    `min liquidity ${state.filters.minLiquidityRating.toFixed(1)} / 5`,
  ];

  loadStatus.textContent = `${filteredCount} of ${state.items.length} items shown • ${filterBits.join(" • ")}`;
}

function renderRows() {
  if (!tableBody) {
    throw new Error("Could not find #data-table tbody");
  }

  const direction = state.sortDirection === "asc" ? 1 : -1;
  const filteredItems = getFilteredItems();
  const sortedItems = [...filteredItems].sort(([, leftData], [, rightData]) => {
    const leftValue = getSortValue(leftData, state.sortKey);
    const rightValue = getSortValue(rightData, state.sortKey);

    if (leftValue === rightValue) {
      return (Number(leftData.profit ?? 0) - Number(rightData.profit ?? 0)) * direction;
    }

    return (leftValue - rightValue) * direction;
  });

  tableBody.innerHTML = "";

  if (sortedItems.length === 0) {
    const emptyRow = document.createElement("tr");
    emptyRow.innerHTML = `
      <td class="empty-state" colspan="3">
        No items matched the current filter settings.
      </td>
    `;
    tableBody.appendChild(emptyRow);
    updateFilterSummary(0);
    return;
  }

  sortedItems.forEach(([itemName, itemData]) => {
    const liquidityRating = Number(itemData["liquidity rating"] ?? 0);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${formatNumber(itemData.profit)}</td>
      <td>${itemName}</td>
      <td>
        <span class="liquidity-badge" title="Raw liquidity score: ${formatNumber(itemData["liquidity score"])}">
          ${liquidityRating.toFixed(1)} / 5
        </span>
      </td>
    `;
    tableBody.appendChild(row);
  });

  updateFilterSummary(sortedItems.length);
}

function setStatus(message, isError = false) {
  if (!loadStatus) {
    return;
  }

  loadStatus.textContent = message;
  loadStatus.classList.toggle("is-error", isError);
}

function syncFilterInputs() {
  if (minProfitInput instanceof HTMLInputElement) {
    minProfitInput.value = String(state.filters.minProfit);
  }

  if (minLiquidityInput instanceof HTMLInputElement) {
    minLiquidityInput.value = String(state.filters.minLiquidityRating);
  }

  if (minLiquidityValue) {
    minLiquidityValue.textContent = `${state.filters.minLiquidityRating.toFixed(1)} / 5`;
  }
}

function setupSorting() {
  sortableHeaders.forEach((header) => {
    header.addEventListener("click", () => {
      const sortKey = header.dataset.sortKey;
      if (!sortKey) {
        return;
      }

      if (state.sortKey === sortKey) {
        state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = sortKey;
        state.sortDirection = "desc";
      }

      updateSortHeaders();
      renderRows();
    });
  });

  updateSortHeaders();
}

function setupSettings() {
  settingsToggle?.addEventListener("click", () => {
    if (!settingsPanel || !settingsToggle) {
      return;
    }

    state.isSettingsOpen = !state.isSettingsOpen;
    syncSettingsPanel();
    saveSettings();
  });

  minProfitInput?.addEventListener("input", (event) => {
    const nextValue = Number(event.target.value);
    state.filters.minProfit = Number.isFinite(nextValue) ? Math.max(0, nextValue) : 0;
    syncFilterInputs();
    saveSettings();
    renderRows();
  });

  minLiquidityInput?.addEventListener("input", (event) => {
    const nextValue = Number(event.target.value);
    state.filters.minLiquidityRating = clamp(
      Number.isFinite(nextValue) ? nextValue : 0,
      0,
      5,
    );
    syncFilterInputs();
    saveSettings();
    renderRows();
  });

  syncFilterInputs();
  syncSettingsPanel();
}

async function loadTableData() {
  try {
    const response = await fetch(API_URL);
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const jsonData = await response.json();
    state.items = Object.entries(jsonData);

    loadStatus?.classList.remove("is-error");
    renderRows();
  } catch (error) {
    console.error("Error loading table data:", error);
    state.items = [];
    renderRows();
    setStatus("Could not load live flip data", true);
  }
}

loadStoredSettings();
setupSorting();
setupSettings();
loadTableData();
