import assert from "node:assert/strict";
import { loadConnection } from "./connection.mjs";
import { chromium } from "playwright-core";
const base = process.argv[2] || "http://127.0.0.1:3001";
const config = await loadConnection();
const headers = { "X-DataView-Worker": config.worker, Authorization: `Bearer ${config.key}` };
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(base + "/#" + new URLSearchParams({ worker: config.worker, key: config.key }));
  await page.locator("summary").filter({ hasText: "เชื่อมต่อแล้ว" }).waitFor({ timeout: 30_000 });
  assert.equal(new URL(page.url()).hash, "");
  assert.equal(await page.title(), "DataView by Cheese Ponrakit");
  await page.getByLabel(/ลิงก์ช่องหรือโปรไฟล์/).fill("https://www.youtube.com/@Google/videos");
  await page.getByLabel("วิดีโอปกติ", { exact: true }).uncheck();
  await page.getByRole("button", { name: "เริ่มวิเคราะห์" }).click();
  await page.getByRole("alert").filter({ hasText: "กรุณาเลือกประเภทคลิป" }).waitFor();
  await page.getByLabel("วิดีโอปกติ", { exact: true }).check();
  await page.getByLabel("จำนวนคลิป", { exact: true }).fill("2");
  await page.getByRole("button", { name: "เริ่มวิเคราะห์" }).click();
  await Promise.race([
    page.locator("tbody tr").first().waitFor({ timeout: 90_000 }),
    page.locator(".error-box").waitFor({ timeout: 90_000 }).then(async () => { throw new Error(await page.locator(".error-box").innerText()); }),
  ]);
  assert.equal(await page.locator("tbody tr").count(), 2);
  assert.equal(await page.locator(".result-source a").getAttribute("href"), "https://www.youtube.com/@Google/videos");
  await page.screenshot({ path: "test-results/result-desktop.png", fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/result-mobile.png", fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.getByRole("button", { name: /TikTok/ }).click();
  assert.equal(await page.locator(".youtube-options").count(), 0);
  await page.getByLabel("เลือกคลิปที่ต้องการวิเคราะห์").selectOption("days");
  await page.getByLabel("จำนวนวันย้อนหลัง", { exact: true }).fill("7");
  await page.getByLabel("เลือกคลิปที่ต้องการวิเคราะห์").selectOption("all");
  assert.equal(await page.locator("#amount").count(), 0);
  await page.getByLabel(/ลิงก์ช่องหรือโปรไฟล์/).fill("https://www.tiktok.com/@jopun");
  await page.getByRole("button", { name: "เริ่มวิเคราะห์" }).click();
  await page.getByRole("button", { name: "ยกเลิก", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "ยกเลิกการวิเคราะห์แล้ว" }).waitFor();
  assert.equal(await page.getByRole("button", { name: "เริ่มวิเคราะห์" }).isEnabled(), true);
  const bad = await page.request.post(`${base}/api/analyze`, { headers, data: { platform: "TikTok", url: "http://127.0.0.1", mode: "latest", amount: 10 } });
  assert.equal(bad.status(), 400);
  const crossOrigin = await page.request.post(`${base}/api/analyze`, { headers: { ...headers, Origin: "https://example.com" }, data: {} });
  assert.equal(crossOrigin.status(), 403);
  assert.deepEqual(errors, []);
  console.log("PASS: real YouTube results, input validation, mobile layout, mode switches, cancellation, invalid URL and origin rejection; no browser errors.");
} finally { await browser.close(); }
