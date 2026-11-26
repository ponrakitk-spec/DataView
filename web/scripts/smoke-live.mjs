// Calls the deployed web API and the user's actual Chrome worker. Never prints connection keys.
import { loadConnection } from "./connection.mjs";
import { randomUUID } from "node:crypto";
const base = process.argv[2] || "http://127.0.0.1:3001";
const selected = process.argv[3];
const resumeJobId = process.argv[4];
const config = await loadConnection();
const headers = { "Content-Type": "application/json", "X-DataView-Worker": config.worker, Authorization: `Bearer ${config.key}` };
const cases = [
  { platform: "YouTube", url: "https://www.youtube.com/@Google/videos", youtubeTabs: ["videos"] },
  { platform: "TikTok", url: "https://www.tiktok.com/@jopun", youtubeTabs: [] },
  { platform: "Facebook", url: "https://www.facebook.com/zuck/reels/", youtubeTabs: [] },
].filter(c => !selected || c.platform === selected);
for (const c of cases) {
  const started = Date.now(), jobId = resumeJobId || randomUUID();
  try {
    console.log(JSON.stringify({ platform: c.platform, jobId, resumed: !!resumeJobId }));
    if (!resumeJobId) {
    const response = await fetch(`${base}/api/analyze`, { method: "POST", headers, body: JSON.stringify({ ...c, mode: "latest", amount: 2, jobId }) });
    const created = await response.json();
    if (!response.ok) throw new Error(created.error || `HTTP ${response.status}`);
    }
    let last = "";
    while (true) {
      const poll = await fetch(`${base}/api/analyze/${jobId}`, { headers });
      const job = await poll.json();
      if (!poll.ok) throw new Error(job.error || `HTTP ${poll.status}`);
      if (job.message !== last) { console.log(JSON.stringify({ platform: c.platform, status: job.status, message: job.message })); last = job.message; }
      if (job.status === "complete") {
        const result = job.result;
        console.log(JSON.stringify({ platform: c.platform, seconds: Math.round((Date.now() - started) / 1000), count: result.videos.length, knownViews: result.knownViews, total: result.totalViews, complete: result.complete, notes: result.notes, videos: result.videos }));
        break;
      }
      if (["error", "cancelled"].includes(job.status)) throw new Error(job.message);
      await new Promise(r => setTimeout(r, 1500));
    }
  } catch (error) {
    console.log(JSON.stringify({ platform: c.platform, jobId, error: error.message, resume: `node scripts/smoke-live.mjs ${base} ${c.platform} ${jobId}` })); process.exitCode = 1;
  }
}
