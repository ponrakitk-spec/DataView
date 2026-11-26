import { readFile } from "node:fs/promises";
export async function loadConnection() {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const config = JSON.parse(await readFile(new URL("../../.dataview/connection.json", import.meta.url), "utf8"));
      const response = await fetch(config.worker + "/health", { headers: { Authorization: `Bearer ${config.key}` }, signal: AbortSignal.timeout(3000) });
      if (response.ok && (await response.json()).status === "online") return config;
    } catch { /* the launcher may still be replacing an expired connection */ }
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error("Local worker is offline. Start worker/start.py before running live checks.");
}
