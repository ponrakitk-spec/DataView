import { test } from "node:test";
import assert from "node:assert/strict";
import { connection, workerRequest, WorkerError, jobIdPattern } from "../src/lib/worker-proxy";
const key = "a".repeat(48);
const req = (worker = "https://sample-worker.trycloudflare.com", extra = {}) => new Request("https://dataview-one.vercel.app/api/analyze", { headers: { "X-DataView-Worker": worker, Authorization: `Bearer ${key}`, ...extra } });
test("connection accepts only an HTTPS Quick Tunnel root and an authenticated token", () => {
  assert.equal(connection(req()).url, "https://sample-worker.trycloudflare.com");
  for (const url of ["http://sample.trycloudflare.com", "https://127.0.0.1", "https://sample.trycloudflare.com.evil.com", "https://user:pass@sample.trycloudflare.com", "https://sample.trycloudflare.com:8765", "https://sample.trycloudflare.com/jobs", "https://sample.trycloudflare.com/?next=x"]) assert.throws(() => connection(req(url)), WorkerError);
  assert.throws(() => connection(req(undefined, { Authorization: "Bearer bad" })), WorkerError);
});
test("cross-origin requests and malformed job IDs are rejected", () => {
  assert.throws(() => connection(req(undefined, { Origin: "https://evil.com" })), (error: unknown) => error instanceof WorkerError && error.status === 403);
  assert.equal(jobIdPattern.test("../../health"), false);
  assert.equal(jobIdPattern.test("12345678-1234-4123-8123-123456789abc"), true);
});
test("proxy passes credentials in headers, never follows redirects and preserves worker errors", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(String(url), "https://sample-worker.trycloudflare.com/jobs");
      assert.equal(options?.redirect, "error");
      assert.equal((options?.headers as Record<string, string>).Authorization, `Bearer ${key}`);
      return Response.json({ status: "queued" });
    };
    assert.deepEqual(await workerRequest(req(), "/jobs", "POST", {}), { status: "queued" });
    globalThis.fetch = async () => Response.json({ error: "รหัสเชื่อมต่อไม่ถูกต้อง" }, { status: 401 });
    await assert.rejects(() => workerRequest(req(), "/jobs"), (error: unknown) => error instanceof WorkerError && error.status === 401);
    globalThis.fetch = async () => new Response("<html>Offline</html>", { status: 502 });
    await assert.rejects(() => workerRequest(req(), "/health"), /ออฟไลน์/);
  } finally { globalThis.fetch = original; }
});
