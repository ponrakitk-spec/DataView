export const platforms = ["YouTube", "TikTok", "Facebook"] as const;
export type Platform = (typeof platforms)[number];
export const youtubeTabs = { videos: "วิดีโอปกติ", shorts: "Shorts", streams: "ไลฟ์ย้อนหลัง" } as const;
export type YoutubeTab = keyof typeof youtubeTabs;
export type Mode = "days" | "latest" | "all";
export const examples: Record<Platform, string> = {
  YouTube: "https://www.youtube.com/@channel/videos",
  TikTok: "https://www.tiktok.com/@username",
  Facebook: "https://www.facebook.com/page/reels/",
};
export interface AnalysisInput {
  platform: Platform;
  url: string;
  mode: Mode;
  amount: number;
  youtubeTabs: YoutubeTab[];
}
export interface Video {
  url: string;
  publishedAt: string | null;
  day: string | null;
  views: number | null;
}
export interface AnalysisResult {
  platform: Platform;
  url: string;
  mode: Mode;
  amount: number;
  youtubeTabs: YoutubeTab[];
  start: string | null;
  end: string | null;
  collectedAt: string;
  complete: boolean;
  notes: string[];
  videos: Video[];
  missingDates: number;
  knownViews: number;
  totalViews: number;
  averageViews: number | null;
}

export function normalizeProfile(platform: Platform, raw: string): string {
  let u: URL;
  try { u = new URL(raw.trim()); } catch { throw new Error("กรุณาใส่ลิงก์ช่องหรือโปรไฟล์ให้ถูกต้อง"); }
  const host = { YouTube: "youtube.com", TikTok: "tiktok.com", Facebook: "facebook.com" }[platform];
  if (!["http:", "https:"].includes(u.protocol) || u.username || u.password || u.port || ![host, `www.${host}`, `m.${host}`].includes(u.hostname)) {
    throw new Error(`กรุณาใส่ลิงก์ของ ${platform} เช่น ${examples[platform]}`);
  }
  const path = u.pathname.replace(/\/+$/, "");
  if (platform === "TikTok" && /^\/@[a-zA-Z0-9_.]+$/.test(path)) return `https://www.tiktok.com${path}`;
  if (platform === "YouTube") {
    const match = path.match(/^(\/@[^/]+|\/(?:channel|user|c)\/[^/]+)(?:\/(?:videos|shorts|streams))?$/);
    if (match) return `https://www.youtube.com${match[1]}/videos`;
  }
  if (platform === "Facebook") {
    const id = u.searchParams.get("id");
    if (path === "/profile.php" && id && /^\d+$/.test(id)) return `https://www.facebook.com/profile.php?id=${id}&sk=reels_tab`;
    const match = path.match(/^\/([\w.%-]+)(?:\/reels(?:_tab)?)?$/);
    if (match && !["reel", "reels", "watch", "groups", "login", "share", "profile.php", "videos"].includes(match[1].toLowerCase())) return `https://www.facebook.com/${match[1]}/reels/`;
  }
  throw new Error(`กรุณาใส่ลิงก์ช่องหรือโปรไฟล์ เช่น ${examples[platform]}`);
}

export function parseInput(raw: unknown): AnalysisInput {
  if (!raw || typeof raw !== "object") throw new Error("ข้อมูลคำขอไม่ถูกต้อง");
  const v = raw as Record<string, unknown>;
  if (!platforms.includes(v.platform as Platform)) throw new Error("กรุณาเลือกแพลตฟอร์มที่รองรับ");
  if (!["days", "latest", "all"].includes(String(v.mode))) throw new Error("กรุณาเลือกรูปแบบการวิเคราะห์");
  if (typeof v.url !== "string" || v.url.length > 2048) throw new Error("กรุณาใส่ลิงก์ช่องหรือโปรไฟล์");
  const amount = v.mode === "all" ? 0 : v.amount;
  if (typeof amount !== "number" || !Number.isSafeInteger(amount) || (v.mode !== "all" && amount < 1)) throw new Error("จำนวนวันหรือจำนวนคลิปต้องเป็นจำนวนเต็มตั้งแต่ 1");
  if (v.mode === "days" && amount > 365000) throw new Error("จำนวนวันย้อนหลังมากเกินช่วงวันที่ที่รองรับ");
  const tabs = v.youtubeTabs;
  if (v.platform === "YouTube" && (!Array.isArray(tabs) || !tabs.length || !tabs.every(t => typeof t === "string" && Object.hasOwn(youtubeTabs, t)))) throw new Error("กรุณาเลือกประเภทคลิป YouTube อย่างน้อยหนึ่งประเภท");
  return { platform: v.platform as Platform, url: normalizeProfile(v.platform as Platform, v.url), mode: v.mode as Mode, amount, youtubeTabs: v.platform === "YouTube" ? [...new Set(tabs as YoutubeTab[])] : [] };
}
