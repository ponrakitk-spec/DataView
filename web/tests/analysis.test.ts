import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeProfile, parseInput, type AnalysisInput } from "../src/lib/analysis";
const input = (overrides: Partial<AnalysisInput> = {}): AnalysisInput => ({ platform: "TikTok", url: "https://www.tiktok.com/@test", mode: "latest", amount: 2, youtubeTabs: [], ...overrides });
test("profile validation strips tracking and rejects credentials, foreign hosts, ports and video URLs", () => {
  assert.equal(normalizeProfile("TikTok", "https://www.tiktok.com/@test/?lang=en"), "https://www.tiktok.com/@test");
  assert.equal(normalizeProfile("YouTube", "https://youtube.com/@test/shorts"), "https://www.youtube.com/@test/videos");
  assert.equal(normalizeProfile("Facebook", "https://www.facebook.com/profile.php?id=123&tracking=1"), "https://www.facebook.com/profile.php?id=123&sk=reels_tab");
  for (const url of ["https://www.tiktok.com.evil.com/@test", "https://user:password@www.tiktok.com/@test", "http://127.0.0.1/@test", "https://www.tiktok.com:8443/@test", "https://www.tiktok.com/@test/video/123", "file:///etc/passwd"]) assert.throws(() => normalizeProfile("TikTok", url));
});
test("input validation requires positive integers and selected YouTube categories", () => {
  for (const amount of [0, -1, 1.2, "10", true, Number.MAX_SAFE_INTEGER + 1]) assert.throws(() => parseInput(input({ amount: amount as number })));
  assert.throws(() => parseInput(input({ platform: "YouTube", url: "https://www.youtube.com/@test" })));
  assert.throws(() => parseInput(input({ platform: "YouTube", url: "https://www.youtube.com/@test", youtubeTabs: ["toString" as never] })));
});
test("full channel has no arbitrary clip cap; categories are deduplicated", () => {
  assert.equal(parseInput(input({ mode: "all", amount: 0 })).amount, 0);
  assert.deepEqual(parseInput(input({ platform: "YouTube", url: "https://youtube.com/@test", youtubeTabs: ["videos", "shorts", "videos", "streams"] })).youtubeTabs, ["videos", "shorts", "streams"]);
});
