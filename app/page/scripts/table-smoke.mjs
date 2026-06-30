import { chromium } from "playwright";

const base = process.env.APP_URL || "http://127.0.0.1:8765";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await page.goto(base, { waitUntil: "networkidle", timeout: 30000 });
await page.waitForSelector("#body tr:not(.skeleton-row)", { timeout: 15000 });

const sample = await page.evaluate(() => {
  const row = document.querySelector("#body tr:not(.skeleton-row)");
  const cells = [...row.querySelectorAll("td")].map((td, i) => ({
    i,
    cls: td.className,
    text: td.innerText.trim(),
    w: Math.round(td.getBoundingClientRect().width),
  }));
  const mid = cells.slice(1, -1);
  const collapsed = mid.filter((c) => c.w < 8).length;
  const emptyText = mid.filter((c) => !c.text).length;
  return {
    cells,
    collapsed,
    emptyText,
    tableMinWidth: getComputedStyle(document.querySelector("table.data-table")).minWidth,
  };
});

if (sample.collapsed > 0) {
  console.error("FAIL: collapsed numeric columns", sample);
  process.exitCode = 1;
} else if (sample.emptyText > 0) {
  console.error("FAIL: empty middle column text", sample);
  process.exitCode = 1;
} else {
  console.log("OK", JSON.stringify({ collapsed: sample.collapsed, tableMinWidth: sample.tableMinWidth, firstMid: sample.cells[1] }, null, 2));
}

await browser.close();
