import "./style.css";

type BazaarItem = {
  item: string;
  display_name: string;
  icon_url: string | null;
  profit: number;
  purchase_price: number | null;
  sale_price: number | null;
  buy_volume: number;
  sell_volume: number;
  instant_buy_volume: number;
  instant_sell_volume: number;
  volume_balance_score: number;
  good_volume_score: number;
  buy_coin_volume: number;
  sell_coin_volume: number;
  coin_balance_score: number;
  matched_coin_volume: number;
  passes_volume_filter: boolean;
};

type ForgeIngredient = {
  item: string;
  display_name: string;
  amount: number;
  bazaar_unit_price?: number | null;
  bazaar_cost?: number | null;
  forgeable?: boolean;
  unit_price?: number | null;
  cost?: number | null;
};

type ForgeItem = {
  item: string;
  display_name: string;
  icon_url: string | null;
  duration: number;
  output_count: number;
  sale_price: number;
  net_revenue: number;
  bazaar_component_cost: number | null;
  bazaar_component_profit: number | null;
  recursive_forge_cost: number | null;
  recursive_forge_profit: number | null;
  recursive_forge_seconds: number | null;
  forged_components: string[];
  raw_components: ForgeIngredient[];
  ingredients: ForgeIngredient[];
};

type SortDirection = "asc" | "desc";
type SortKey = "item" | "profit" | "purchase" | "sale" | "balance" | "matched";
type FilterKey = "all" | "margin" | "balance" | "liquidity" | "watchlist";
type ForgeSortKey =
  | "item"
  | "bazaarProfit"
  | "recursiveProfit"
  | "bazaarCost"
  | "recursiveCost"
  | "sale"
  | "time";
type ForgeFilterKey = "all" | "bazaar" | "recursive" | "profitable";

const get = <T extends Element>(selector: string): T => {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing required element: ${selector}`);
  return element;
};

const searchInput = get<HTMLInputElement>("#search");
const resultCount = get<HTMLParagraphElement>("#result-count");
const itemsBody = get<HTMLTableSectionElement>("#items");
const marketTable = get<HTMLTableElement>(".market-table");
const dataState = get<HTMLDivElement>("#data-state");
const loadingState = get<HTMLDivElement>("#loading-state");
const errorState = get<HTMLDivElement>("#error-state");
const refreshButton = get<HTMLButtonElement>("#refresh");
const retryButton = get<HTMLButtonElement>("#retry");
const updatedAt = get<HTMLSpanElement>("#updated-at");
const drawer = get<HTMLElement>("#signal-drawer");
const drawerBackdrop = get<HTMLDivElement>("#drawer-backdrop");
const drawerContent = get<HTMLDivElement>("#drawer-content");
const drawerClose = get<HTMLButtonElement>("#drawer-close");
const drawerKicker = get<HTMLParagraphElement>("#drawer-kicker");
const filterButtons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-filter]"));
const sortButtons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-sort]"));
const forgeSearchInput = get<HTMLInputElement>("#forge-search");
const forgeResultCount = get<HTMLParagraphElement>("#forge-result-count");
const forgeItemsBody = get<HTMLTableSectionElement>("#forge-items");
const forgeTable = get<HTMLTableElement>(".forge-table");
const forgeDataState = get<HTMLDivElement>("#forge-data-state");
const forgeLoadingState = get<HTMLDivElement>("#forge-loading-state");
const forgeErrorState = get<HTMLDivElement>("#forge-error-state");
const forgeRetryButton = get<HTMLButtonElement>("#forge-retry");
const forgeFilterButtons = Array.from(
  document.querySelectorAll<HTMLButtonElement>("[data-forge-filter]"),
);
const forgeSortButtons = Array.from(
  document.querySelectorAll<HTMLButtonElement>("[data-forge-sort]"),
);

let allItems: BazaarItem[] = [];
let activeFilter: FilterKey = "all";
let sortState: { key: SortKey; direction: SortDirection } = {
  key: "matched",
  direction: "desc",
};
let watchedItems = new Set<string>(readWatchlist());
let selectedItem: BazaarItem | null = null;
let allForgeItems: ForgeItem[] = [];
let activeForgeFilter: ForgeFilterKey = "all";
let forgeSortState: { key: ForgeSortKey; direction: SortDirection } = {
  key: "recursiveProfit",
  direction: "desc",
};

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const EMPTY_IMAGE =
  "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

function readWatchlist(): string[] {
  try {
    return JSON.parse(localStorage.getItem("bazaar-lens-watchlist") ?? "[]") as string[];
  } catch {
    return [];
  }
}

function persistWatchlist(): void {
  localStorage.setItem("bazaar-lens-watchlist", JSON.stringify([...watchedItems]));
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return entities[character];
  });
}

function formatItemName(value: string): string {
  if (value.includes("_") && value === value.toUpperCase()) {
    return value
      .split("_")
      .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
      .join(" ");
  }
  return value;
}

function formatCoins(value: number | null, abbreviated = false): string {
  if (value === null) return "—";
  return `${abbreviated ? compact.format(value) : number.format(value)} coins`;
}

function formatSignedCoins(value: number, abbreviated = false): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${abbreviated ? compact.format(value) : number.format(value)} coins`;
}

function formatOptionalSignedCoins(value: number | null, abbreviated = false): string {
  return value === null ? "—" : formatSignedCoins(value, abbreviated);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const roundedSeconds = Math.round(seconds);
  const days = Math.floor(roundedSeconds / 86_400);
  const hours = Math.floor((roundedSeconds % 86_400) / 3_600);
  const minutes = Math.floor((roundedSeconds % 3_600) / 60);
  const remainder = roundedSeconds % 60;
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  if (!parts.length || remainder) parts.push(`${remainder}s`);
  return parts.slice(0, 2).join(" ");
}

function getMarginPercent(item: BazaarItem): number {
  if (!item.purchase_price || item.purchase_price <= 0) return 0;
  return item.profit / item.purchase_price;
}

function getIconUrl(item: { item: string; icon_url: string | null }): string {
  return item.icon_url ?? `/api/icons/${encodeURIComponent(item.item)}`;
}

function renderMetrics(): void {
  const totalLiquidity = allItems.reduce((sum, item) => sum + item.matched_coin_volume, 0);
  const averageBalance = allItems.length
    ? allItems.reduce((sum, item) => sum + item.coin_balance_score, 0) / allItems.length
    : 0;
  const profits = allItems.map((item) => item.profit).sort((a, b) => a - b);
  const midpoint = Math.floor(profits.length / 2);
  const medianProfit = profits.length
    ? profits.length % 2
      ? profits[midpoint]
      : (profits[midpoint - 1] + profits[midpoint]) / 2
    : 0;

  get<HTMLElement>("#metric-markets").textContent = integer.format(allItems.length);
  get<HTMLElement>("#metric-liquidity").textContent = formatCoins(totalLiquidity, true);
  get<HTMLElement>("#metric-spread").textContent = formatCoins(medianProfit, true);
  get<HTMLElement>("#metric-balance").textContent = formatPercent(averageBalance);
}

function matchesFilter(item: BazaarItem): boolean {
  switch (activeFilter) {
    case "margin":
      return getMarginPercent(item) >= 0.05;
    case "balance":
      return item.coin_balance_score >= 0.97;
    case "liquidity":
      return item.matched_coin_volume >= 500_000_000;
    case "watchlist":
      return watchedItems.has(item.item);
    case "all":
    default:
      return true;
  }
}

function getSortValue(item: BazaarItem, key: SortKey): string | number {
  switch (key) {
    case "item":
      return item.display_name.toLowerCase();
    case "profit":
      return item.profit;
    case "purchase":
      return item.purchase_price ?? Number.NEGATIVE_INFINITY;
    case "sale":
      return item.sale_price ?? Number.NEGATIVE_INFINITY;
    case "balance":
      return item.coin_balance_score;
    case "matched":
    default:
      return item.matched_coin_volume;
  }
}

function sortItems(items: BazaarItem[]): BazaarItem[] {
  const direction = sortState.direction === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    const aValue = getSortValue(a, sortState.key);
    const bValue = getSortValue(b, sortState.key);
    if (typeof aValue === "string" && typeof bValue === "string") {
      return aValue.localeCompare(bValue) * direction;
    }
    return (Number(aValue) - Number(bValue)) * direction;
  });
}

function visibleItems(): BazaarItem[] {
  const query = searchInput.value.trim().toLowerCase();
  return sortItems(
    allItems.filter(
      (item) =>
        matchesFilter(item) &&
        (item.item.toLowerCase().includes(query) || item.display_name.toLowerCase().includes(query)),
    ),
  );
}

function updateSortUi(): void {
  for (const button of sortButtons) {
    const key = button.dataset.sort as SortKey;
    const active = key === sortState.key;
    button.dataset.direction = active ? sortState.direction : "";
    button.closest("th")?.setAttribute(
      "aria-sort",
      active ? (sortState.direction === "asc" ? "ascending" : "descending") : "none",
    );
  }
}

function renderItemRow(item: BazaarItem): string {
  const margin = getMarginPercent(item);
  const isWatched = watchedItems.has(item.item);
  const safeName = escapeHtml(formatItemName(item.display_name));
  return `
    <tr>
      <td data-label="Market">
        <button class="market-cell" type="button" data-open-item="${escapeHtml(item.item)}">
          <span class="item-icon-frame">
            <img
              src="${escapeHtml(getIconUrl(item))}"
              alt=""
              loading="lazy"
              width="38"
              height="38"
              onerror="this.src='${EMPTY_IMAGE}'; this.classList.add('item-icon--empty');"
            />
          </span>
          <span class="market-name">
            <strong>${safeName}</strong>
            <small>${escapeHtml(item.item)}</small>
          </span>
        </button>
      </td>
      <td class="numeric" data-label="Net spread">
        <strong class="profit-value">${formatSignedCoins(item.profit).replace(" coins", "")}</strong>
        <small>${margin >= 0 ? "+" : ""}${(margin * 100).toFixed(2)}%</small>
      </td>
      <td class="numeric" data-label="Buy order">
        <strong>${item.purchase_price === null ? "—" : number.format(item.purchase_price)}</strong>
        <small>coins / unit</small>
      </td>
      <td class="numeric" data-label="Sell offer">
        <strong>${item.sale_price === null ? "—" : number.format(item.sale_price)}</strong>
        <small>coins / unit</small>
      </td>
      <td data-label="Flow balance">
        <div class="balance-cell">
          <div class="balance-cell__label"><strong>${formatPercent(item.coin_balance_score)}</strong><small>balanced</small></div>
          <span class="balance-track"><span style="width:${Math.min(100, item.coin_balance_score * 100)}%"></span></span>
        </div>
      </td>
      <td class="numeric" data-label="Matched / week">
        <strong>${formatCoins(item.matched_coin_volume, true)}</strong>
        <small>${compact.format(item.buy_volume + item.sell_volume)} units</small>
      </td>
      <td class="watch-cell">
        <button
          class="watch-button${isWatched ? " is-watched" : ""}"
          type="button"
          data-watch-item="${escapeHtml(item.item)}"
          aria-label="${isWatched ? "Remove" : "Add"} ${safeName} ${isWatched ? "from" : "to"} watchlist"
          aria-pressed="${isWatched}"
        >${isWatched ? "★" : "☆"}</button>
      </td>
    </tr>`;
}

function renderItems(): void {
  const items = visibleItems();
  resultCount.textContent = `${integer.format(items.length)} of ${integer.format(allItems.length)} markets`;
  updateSortUi();

  if (items.length === 0) {
    itemsBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7">
          <span>◇</span>
          <strong>No signals found</strong>
          <small>Try a broader filter or a different search.</small>
        </td>
      </tr>`;
    return;
  }
  itemsBody.innerHTML = items.map(renderItemRow).join("");
}

function forgeMatchesFilter(item: ForgeItem): boolean {
  switch (activeForgeFilter) {
    case "bazaar":
      return item.bazaar_component_cost !== null;
    case "recursive":
      return item.recursive_forge_cost !== null;
    case "profitable":
      return (item.bazaar_component_profit ?? Number.NEGATIVE_INFINITY) > 0 ||
        (item.recursive_forge_profit ?? Number.NEGATIVE_INFINITY) > 0;
    case "all":
    default:
      return true;
  }
}

function getForgeSortValue(item: ForgeItem, key: ForgeSortKey): string | number {
  switch (key) {
    case "item":
      return item.display_name.toLowerCase();
    case "bazaarProfit":
      return item.bazaar_component_profit ?? Number.NEGATIVE_INFINITY;
    case "bazaarCost":
      return item.bazaar_component_cost ?? Number.NEGATIVE_INFINITY;
    case "recursiveCost":
      return item.recursive_forge_cost ?? Number.NEGATIVE_INFINITY;
    case "sale":
      return item.sale_price;
    case "time":
      return item.duration;
    case "recursiveProfit":
    default:
      return item.recursive_forge_profit ?? Number.NEGATIVE_INFINITY;
  }
}

function visibleForgeItems(): ForgeItem[] {
  const query = forgeSearchInput.value.trim().toLowerCase();
  const direction = forgeSortState.direction === "asc" ? 1 : -1;
  return allForgeItems
    .filter(
      (item) =>
        forgeMatchesFilter(item) &&
        (item.item.toLowerCase().includes(query) || item.display_name.toLowerCase().includes(query)),
    )
    .sort((a, b) => {
      const aValue = getForgeSortValue(a, forgeSortState.key);
      const bValue = getForgeSortValue(b, forgeSortState.key);
      if (typeof aValue === "string" && typeof bValue === "string") {
        return aValue.localeCompare(bValue) * direction;
      }
      return (Number(aValue) - Number(bValue)) * direction;
    });
}

function updateForgeSortUi(): void {
  for (const button of forgeSortButtons) {
    const key = button.dataset.forgeSort as ForgeSortKey;
    const active = key === forgeSortState.key;
    button.dataset.direction = active ? forgeSortState.direction : "";
    button.closest("th")?.setAttribute(
      "aria-sort",
      active ? (forgeSortState.direction === "asc" ? "ascending" : "descending") : "none",
    );
  }
}

function profitClass(value: number | null): string {
  if (value === null) return "";
  return value >= 0 ? "profit-value" : "loss-value";
}

function profitMargin(profit: number | null, cost: number | null): string {
  if (profit === null || cost === null || cost <= 0) return "route unavailable";
  return `${profit >= 0 ? "+" : ""}${((profit / cost) * 100).toFixed(1)}% on cost`;
}

function renderForgeRow(item: ForgeItem): string {
  const safeName = escapeHtml(formatItemName(item.display_name));
  return `
    <tr>
      <td data-label="Forge item">
        <button class="market-cell" type="button" data-open-forge="${escapeHtml(item.item)}">
          <span class="item-icon-frame">
            <img
              src="${escapeHtml(getIconUrl(item))}"
              alt=""
              loading="lazy"
              width="38"
              height="38"
              onerror="this.src='${EMPTY_IMAGE}'; this.classList.add('item-icon--empty');"
            />
          </span>
          <span class="market-name">
            <strong>${safeName}</strong>
            <small>${escapeHtml(item.item)}</small>
          </span>
        </button>
      </td>
      <td class="numeric" data-label="Bazaar parts profit">
        <strong class="${profitClass(item.bazaar_component_profit)}">${formatOptionalSignedCoins(item.bazaar_component_profit, true).replace(" coins", "")}</strong>
        <small>${profitMargin(item.bazaar_component_profit, item.bazaar_component_cost)}</small>
      </td>
      <td class="numeric forge-chain-cell" data-label="Forge-chain profit">
        <strong class="${profitClass(item.recursive_forge_profit)}">${formatOptionalSignedCoins(item.recursive_forge_profit, true).replace(" coins", "")}</strong>
        <small>${profitMargin(item.recursive_forge_profit, item.recursive_forge_cost)}</small>
      </td>
      <td class="numeric" data-label="Bazaar parts cost">
        <strong>${item.bazaar_component_cost === null ? "—" : number.format(item.bazaar_component_cost)}</strong>
        <small>immediate parts</small>
      </td>
      <td class="numeric" data-label="Forge-chain cost">
        <strong>${item.recursive_forge_cost === null ? "—" : number.format(item.recursive_forge_cost)}</strong>
        <small>${integer.format(item.forged_components.length)} forged component${item.forged_components.length === 1 ? "" : "s"}</small>
      </td>
      <td class="numeric" data-label="Bazaar sell">
        <strong>${number.format(item.sale_price)}</strong>
        <small>instant sell / unit</small>
      </td>
      <td class="numeric" data-label="Final forge">
        <strong>${formatDuration(item.duration)}</strong>
        <small>${item.output_count === 1 ? "one output" : `${number.format(item.output_count)} outputs`}</small>
      </td>
    </tr>`;
}

function renderForgeItems(): void {
  const items = visibleForgeItems();
  forgeResultCount.textContent = `${integer.format(items.length)} of ${integer.format(allForgeItems.length)} Bazaar exits`;
  updateForgeSortUi();

  if (items.length === 0) {
    forgeItemsBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7">
          <span>◇</span>
          <strong>No Forge routes found</strong>
          <small>Try a broader route filter or search.</small>
        </td>
      </tr>`;
    return;
  }
  forgeItemsBody.innerHTML = items.map(renderForgeRow).join("");
}

function setForgeFilter(filter: ForgeFilterKey): void {
  activeForgeFilter = filter;
  for (const button of forgeFilterButtons) {
    button.classList.toggle("is-active", button.dataset.forgeFilter === filter);
  }
  renderForgeItems();
}

function setForgeSort(key: ForgeSortKey): void {
  forgeSortState = {
    key,
    direction:
      forgeSortState.key === key
        ? forgeSortState.direction === "asc"
          ? "desc"
          : "asc"
        : key === "item"
          ? "asc"
          : "desc",
  };
  renderForgeItems();
}

function setFilter(filter: FilterKey): void {
  activeFilter = filter;
  for (const button of filterButtons) {
    button.classList.toggle("is-active", button.dataset.filter === filter);
  }
  renderItems();
}

function setSort(key: SortKey): void {
  sortState = {
    key,
    direction:
      sortState.key === key ? (sortState.direction === "asc" ? "desc" : "asc") : key === "item" ? "asc" : "desc",
  };
  renderItems();
}

function toggleWatchlist(itemId: string): void {
  if (watchedItems.has(itemId)) watchedItems.delete(itemId);
  else watchedItems.add(itemId);
  persistWatchlist();
  renderItems();
  if (selectedItem?.item === itemId) renderDrawer(selectedItem);
}

function signalLabel(item: BazaarItem): string {
  if (item.coin_balance_score >= 0.98 && getMarginPercent(item) >= 0.05) return "Prime setup";
  if (item.coin_balance_score >= 0.97) return "Tight flow";
  if (item.matched_coin_volume >= 500_000_000) return "Deep market";
  return "Balanced market";
}

function renderDrawer(item: BazaarItem): void {
  const isWatched = watchedItems.has(item.item);
  drawerContent.innerHTML = `
    <div class="drawer-title-row">
      <span class="drawer-icon"><img src="${escapeHtml(getIconUrl(item))}" alt="" width="52" height="52" /></span>
      <div>
        <span class="signal-pill">${signalLabel(item)}</span>
        <h2 id="drawer-title">${escapeHtml(formatItemName(item.display_name))}</h2>
        <p>${escapeHtml(item.item)}</p>
      </div>
    </div>
    <div class="drawer-score">
      <div><span>Net spread</span><strong>${formatSignedCoins(item.profit, true)}</strong></div>
      <div><span>Margin</span><strong>+${(getMarginPercent(item) * 100).toFixed(2)}%</strong></div>
    </div>
    <div class="drawer-stats">
      <div><span>Buy order</span><strong>${formatCoins(item.purchase_price)}</strong></div>
      <div><span>Sell offer</span><strong>${formatCoins(item.sale_price)}</strong></div>
      <div><span>Matched weekly</span><strong>${formatCoins(item.matched_coin_volume, true)}</strong></div>
      <div><span>Flow balance</span><strong>${formatPercent(item.coin_balance_score)}</strong></div>
      <div><span>Weekly buy units</span><strong>${integer.format(item.buy_volume)}</strong></div>
      <div><span>Weekly sell units</span><strong>${integer.format(item.sell_volume)}</strong></div>
    </div>
    <div class="drawer-insight">
      <span>Lens read</span>
      <p>${formatPercent(item.coin_balance_score)} of coin flow is balanced across both sides, with ${formatCoins(item.matched_coin_volume, true)} in matched weekly liquidity.</p>
    </div>
    <button class="drawer-watch${isWatched ? " is-watched" : ""}" type="button" data-watch-item="${escapeHtml(item.item)}">
      ${isWatched ? "★ Remove from watchlist" : "☆ Add to watchlist"}
    </button>`;
}

function renderIngredientList(
  ingredients: ForgeIngredient[],
  route: "bazaar" | "raw",
): string {
  if (!ingredients.length) return `<p class="ingredient-empty">Route unavailable.</p>`;
  return ingredients
    .map((ingredient) => {
      const cost = route === "bazaar" ? ingredient.bazaar_cost : ingredient.cost;
      return `
        <li>
          <span class="ingredient-quantity">${number.format(ingredient.amount)}×</span>
          <span class="ingredient-name">
            <strong>${escapeHtml(formatItemName(ingredient.display_name))}</strong>
            <small>${escapeHtml(ingredient.item)}${ingredient.forgeable ? " · forgeable" : ""}</small>
          </span>
          <span class="ingredient-cost">${formatCoins(cost ?? null, true)}</span>
        </li>`;
    })
    .join("");
}

function renderForgeDrawer(item: ForgeItem): void {
  const forgedNames = item.forged_components.map(formatItemName);
  drawerContent.innerHTML = `
    <div class="drawer-title-row">
      <span class="drawer-icon"><img src="${escapeHtml(getIconUrl(item))}" alt="" width="52" height="52" /></span>
      <div>
        <span class="signal-pill">Bazaar-priced output</span>
        <h2 id="drawer-title">${escapeHtml(formatItemName(item.display_name))}</h2>
        <p>${escapeHtml(item.item)}</p>
      </div>
    </div>
    <div class="drawer-score forge-drawer-score">
      <div><span>Bazaar parts profit</span><strong class="${profitClass(item.bazaar_component_profit)}">${formatOptionalSignedCoins(item.bazaar_component_profit, true)}</strong></div>
      <div><span>Forge-chain profit</span><strong class="${profitClass(item.recursive_forge_profit)}">${formatOptionalSignedCoins(item.recursive_forge_profit, true)}</strong></div>
    </div>
    <div class="drawer-stats">
      <div><span>Bazaar parts cost</span><strong>${formatCoins(item.bazaar_component_cost, true)}</strong></div>
      <div><span>Forge-chain cost</span><strong>${formatCoins(item.recursive_forge_cost, true)}</strong></div>
      <div><span>Bazaar instant sell</span><strong>${formatCoins(item.sale_price, true)}</strong></div>
      <div><span>Revenue after tax</span><strong>${formatCoins(item.net_revenue, true)}</strong></div>
      <div><span>Final Forge time</span><strong>${formatDuration(item.duration)}</strong></div>
      <div><span>Total chain slot time</span><strong>${formatDuration(item.recursive_forge_seconds)}</strong></div>
    </div>
    <div class="ingredient-section">
      <div class="ingredient-heading">
        <span>Bazaar parts route</span>
        <small>Immediate recipe components</small>
      </div>
      <ul class="ingredient-list">${renderIngredientList(item.ingredients, "bazaar")}</ul>
    </div>
    <div class="ingredient-section">
      <div class="ingredient-heading">
        <span>Forge-chain raw basket</span>
        <small>Bazaar-priced terminal materials</small>
      </div>
      <ul class="ingredient-list">${renderIngredientList(item.raw_components, "raw")}</ul>
    </div>
    <div class="drawer-insight">
      <span>Route separation</span>
      <p>${
        forgedNames.length
          ? `The Forge-chain route forges ${escapeHtml(forgedNames.join(", "))} before the final item. Its cost is not used in the Bazaar-parts profit.`
          : "This recipe has no forgeable sub-components, so both available routes use the same Bazaar-priced raw basket."
      }</p>
    </div>`;
}

function openDrawer(itemId: string): void {
  const item = allItems.find((candidate) => candidate.item === itemId);
  if (!item) return;
  drawerKicker.textContent = "Signal detail";
  selectedItem = item;
  renderDrawer(item);
  drawer.hidden = false;
  drawerBackdrop.hidden = false;
  requestAnimationFrame(() => {
    drawer.classList.add("is-open");
    drawerBackdrop.classList.add("is-open");
  });
  drawer.setAttribute("aria-hidden", "false");
  drawerClose.focus();
}

function openForgeDrawer(itemId: string): void {
  const item = allForgeItems.find((candidate) => candidate.item === itemId);
  if (!item) return;
  selectedItem = null;
  drawerKicker.textContent = "Forge route detail";
  renderForgeDrawer(item);
  drawer.hidden = false;
  drawerBackdrop.hidden = false;
  requestAnimationFrame(() => {
    drawer.classList.add("is-open");
    drawerBackdrop.classList.add("is-open");
  });
  drawer.setAttribute("aria-hidden", "false");
  drawerClose.focus();
}

function closeDrawer(): void {
  drawer.classList.remove("is-open");
  drawerBackdrop.classList.remove("is-open");
  drawer.setAttribute("aria-hidden", "true");
  window.setTimeout(() => {
    drawer.hidden = true;
    drawerBackdrop.hidden = true;
  }, 220);
}

function setLoading(isLoading: boolean): void {
  dataState.setAttribute("aria-busy", String(isLoading));
  loadingState.hidden = !isLoading;
}

function setForgeLoading(isLoading: boolean): void {
  forgeDataState.setAttribute("aria-busy", String(isLoading));
  forgeLoadingState.hidden = !isLoading;
}

async function loadItems(): Promise<void> {
  setLoading(true);
  errorState.hidden = true;
  marketTable.hidden = true;
  resultCount.textContent = "Syncing live market…";

  try {
    const response = await fetch("/api/items", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Market request failed with status ${response.status}`);
    const data = (await response.json()) as Record<string, BazaarItem>;
    allItems = Object.values(data);
    renderMetrics();
    renderItems();
    marketTable.hidden = false;
    updatedAt.textContent = `Updated ${new Intl.DateTimeFormat("en", {
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date())}`;
  } catch (error) {
    console.error(error);
    errorState.hidden = false;
    resultCount.textContent = "Market unavailable";
    updatedAt.textContent = "Connection issue";
  } finally {
    setLoading(false);
  }
}

async function loadForgeItems(): Promise<void> {
  setForgeLoading(true);
  forgeErrorState.hidden = true;
  forgeTable.hidden = true;
  forgeResultCount.textContent = "Calculating separate cost routes…";

  try {
    const response = await fetch("/api/forge", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Forge request failed with status ${response.status}`);
    allForgeItems = (await response.json()) as ForgeItem[];
    renderForgeItems();
    forgeTable.hidden = false;
  } catch (error) {
    console.error(error);
    forgeErrorState.hidden = false;
    forgeResultCount.textContent = "Forge calculation unavailable";
  } finally {
    setForgeLoading(false);
  }
}

async function loadAll(): Promise<void> {
  refreshButton.disabled = true;
  refreshButton.classList.add("is-loading");
  await Promise.all([loadItems(), loadForgeItems()]);
  refreshButton.disabled = false;
  refreshButton.classList.remove("is-loading");
}

searchInput.addEventListener("input", renderItems);
forgeSearchInput.addEventListener("input", renderForgeItems);
refreshButton.addEventListener("click", loadAll);
retryButton.addEventListener("click", loadAll);
forgeRetryButton.addEventListener("click", loadAll);
drawerClose.addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", closeDrawer);

for (const button of filterButtons) {
  button.addEventListener("click", () => setFilter(button.dataset.filter as FilterKey));
}
for (const button of sortButtons) {
  button.addEventListener("click", () => setSort(button.dataset.sort as SortKey));
}
for (const button of forgeFilterButtons) {
  button.addEventListener("click", () =>
    setForgeFilter(button.dataset.forgeFilter as ForgeFilterKey),
  );
}
for (const button of forgeSortButtons) {
  button.addEventListener("click", () => setForgeSort(button.dataset.forgeSort as ForgeSortKey));
}

document.addEventListener("click", (event) => {
  const target = event.target as HTMLElement;
  const watchButton = target.closest<HTMLButtonElement>("[data-watch-item]");
  if (watchButton) {
    event.stopPropagation();
    toggleWatchlist(watchButton.dataset.watchItem ?? "");
    return;
  }
  const itemButton = target.closest<HTMLButtonElement>("[data-open-item]");
  if (itemButton) openDrawer(itemButton.dataset.openItem ?? "");
  const forgeButton = target.closest<HTMLButtonElement>("[data-open-forge]");
  if (forgeButton) openForgeDrawer(forgeButton.dataset.openForge ?? "");
});

document.addEventListener("keydown", (event) => {
  const target = event.target as HTMLElement;
  if (event.key === "/" && target.tagName !== "INPUT") {
    event.preventDefault();
    searchInput.focus();
  }
  if (event.key === "Escape") {
    if (drawer.classList.contains("is-open")) closeDrawer();
    else if (document.activeElement === searchInput) searchInput.blur();
  }
});

void loadAll();
