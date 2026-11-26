"""Collect public video metrics by date, latest count, or full profile."""

import base64
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time as day_time
from decimal import Decimal
from itertools import count
from urllib.parse import parse_qs, urlsplit

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException

from tiktok10Latest import BANGKOK, ProfileCollector, parse_nonnegative_int, validate_profile_url


PLATFORMS = ("YouTube", "TikTok", "Facebook")
YOUTUBE_TABS = {"videos": "วิดีโอปกติ", "shorts": "Shorts", "streams": "ไลฟ์ย้อนหลัง"}
EXAMPLES = {
    "YouTube": "https://www.youtube.com/@channel/videos",
    "TikTok": "https://www.tiktok.com/@username",
    "Facebook": "https://www.facebook.com/page/reels/",
}


def profile_url(platform, raw):
    p = urlsplit(raw.strip())
    host = {"YouTube": "youtube.com", "TikTok": "tiktok.com", "Facebook": "facebook.com"}[platform]
    allowed = {host, "www." + host, "m." + host}
    if p.scheme not in ("http", "https") or p.netloc.lower() not in allowed:
        raise ValueError(f"กรุณาใส่ลิงก์ของ {platform} เช่น {EXAMPLES[platform]}")
    path = p.path.rstrip("/")
    if platform == "TikTok" and re.fullmatch(r"/@[\w.]+", path, re.ASCII):
        return validate_profile_url("https://www.tiktok.com" + path)[0]
    if platform == "YouTube":
        match = re.fullmatch(r"(/@[^/]+|/(?:channel|user|c)/[^/]+)(?:/(?:videos|shorts|streams))?", path)
        if match:
            return "https://www.youtube.com" + match[1] + "/videos"
    if platform == "Facebook":
        if path == "/profile.php":
            page_id = parse_qs(p.query).get("id", [""])[0]
            if re.fullmatch(r"[0-9]+", page_id):
                return f"https://www.facebook.com/profile.php?id={page_id}&sk=reels_tab"
        match = re.fullmatch(r"/([\w.%-]+)(?:/reels(?:_tab)?)?", path)
        if match and match[1].lower() not in {"reel", "reels", "watch", "groups", "login", "share", "profile.php", "videos"}:
            return "https://www.facebook.com/" + match[1] + "/reels/"
    raise ValueError(f"กรุณาใส่ลิงก์ช่องหรือโปรไฟล์ เช่น {EXAMPLES[platform]}")


def date_window(value, today=None):
    today = today or datetime.now(BANGKOK).date()
    value = str(value).strip()
    if not value.isdecimal() or len(value) > 7 or not 1 <= int(value) <= today.toordinal():
        raise ValueError("จำนวนวันต้องเป็นจำนวนเต็มตั้งแต่ 1 และอยู่ในช่วงวันที่ที่ใช้งานได้")
    return today - timedelta(days=int(value) - 1), today


@dataclass(frozen=True)
class Video:
    url: str
    day: date | None
    views: int | None
    posted_at: datetime | None = None


@dataclass
class Report:
    start: date | None
    end: date | None
    videos: dict = field(default_factory=dict)
    missing_dates: int = 0
    complete: bool = False
    note: str = ""
    limit: int | None = None

    def add(self, url, published, views):
        stamp = published_time(published)
        day = stamp.date() if stamp else None
        if day is None and (self.start is not None or self.limit is not None):
            self.missing_dates += 1
        elif self.start is None or self.start <= day <= self.end:
            self.videos[url] = Video(url, day, views, stamp)

    def ordered(self):
        # Equal timestamps retain feed order. Missing dates sort last in full-channel mode.
        earliest = datetime.min.replace(tzinfo=BANGKOK)
        return sorted(self.videos.values(), key=lambda v: v.posted_at or earliest, reverse=True)

    def select_latest(self):
        if self.limit is not None:
            self.videos = {v.url: v for v in self.ordered()[:self.limit]}

    def metrics(self):
        values = [video.views for video in self.videos.values() if video.views is not None]
        return len(values), sum(values), sum(values) / len(values) if values else None


def published_time(value):
    try:
        if isinstance(value, datetime):
            return value.astimezone(BANGKOK) if value.tzinfo else None
        if isinstance(value, date):
            return datetime.combine(value, day_time.min, BANGKOK)
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdecimal()):
            return datetime.fromtimestamp(int(value), BANGKOK)
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), day_time.min, BANGKOK)
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone(BANGKOK) if stamp.tzinfo else None
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def posted_day(value):
    stamp = published_time(value)
    return stamp.date() if stamp else None


def labeled_views(text):
    """Only accept a visible count explicitly labelled as plays/views."""
    if not isinstance(text, str):
        return None
    match = re.fullmatch(
        r"\s*(?:(?:ยอดดู|การดู|รับชม|views?|plays?|play count)\s*[:：]?\s*)?"
        r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(พันล้าน|ล้าน|แสน|หมื่น|พัน|[KMB])?"
        r"\s*(?:views?|plays?|การดู|ครั้ง)?\s*", text, re.I)
    if not match or not re.search(r"views?|plays?|ยอดดู|การดู|รับชม", text, re.I):
        return None
    scale = {"K": 1000, "M": 10**6, "B": 10**9, "พัน": 1000, "หมื่น": 10000,
             "แสน": 100000, "ล้าน": 10**6, "พันล้าน": 10**9}
    return int(Decimal(match[1].replace(",", "")) * scale.get((match[2] or "").upper(), 1))


def navigate(driver, url):
    try:
        driver.get(url)
    except TimeoutException:
        pass  # The document may already contain usable metadata.


def collect_tiktok(driver, url, report, progress, check):
    collector = ProfileCollector(driver, url.rsplit("@", 1)[1], report.limit)
    checked = set()
    idle = 0
    for page in count():
        check()
        previous = collector.pages
        began = time.monotonic()
        deadline = began + (90 if page == 0 else 6)
        while time.monotonic() < deadline:
            check()
            collector.poll()
            if collector.pages > previous and not collector.pending:
                break
            if not collector.pages and not collector.pending and time.monotonic() - began >= 8 and driver.execute_script(
                    "return !!document.querySelector('[data-e2e=user-post-item] a[href*=\"/video/\"]')"):
                # Some profiles render the first page into HTML without sending a feed response.
                collect_listing(driver, "TikTok", report, progress, check, url)
                return
            time.sleep(0.4)
        new_ids = [key for key in collector.clips if key not in checked]
        days = []
        for key in new_ids:
            clip = collector.clips[key]
            days.append(clip.posted_at.astimezone(BANGKOK).date())
            report.add(f"{url}/video/{key}", clip.posted_at, clip.views)
        checked.update(new_ids)
        progress(f"TikTok • อ่านแล้ว {len(checked):,} คลิป")
        # A later batch entirely before the start avoids stopping at an old pinned clip.
        before_window = report.start is not None and page > 0 and days and max(days) < report.start
        if collector.exhausted or collector.passed_boundary or before_window:
            report.complete = not collector.failed_responses and not collector.pending
            break
        idle = 0 if new_ids else idle + 1
        if idle >= 3 or (page == 0 and not collector.pages) or (report.start and page >= 100):
            break
        driver.execute_script("window.scrollBy(0,-400); window.scrollTo(0,document.body.scrollHeight)")
    for clip in collector.clips.values():
        report.add(f"{url}/video/{clip.video_id}", clip.posted_at, clip.views)
    for key, views in collector.undated.items():
        report.add(f"{url}/video/{key}", None, views)
    report.missing_dates += len(collector.invalid_items - collector.undated.keys())
    if not report.complete:
        report.note = "TikTok ส่งข้อมูลไม่ครบ หาก Chrome ขอให้ยืนยันตัวตน ให้ยืนยันแล้วลองอีกครั้ง"


LIST_CARDS = """
const platform = arguments[0];
const selectors = {
  YouTube: arguments[1] === 'shorts'
    ? 'ytd-rich-grid-renderer a[href*="/shorts/"], ytd-grid-renderer a[href*="/shorts/"]'
    : 'ytd-rich-grid-renderer ytd-rich-item-renderer a[href*="watch?"], ytd-grid-video-renderer a[href*="watch?"]',
  Facebook: '[role=main] a[href*="/reel/"], main a[href*="/reel/"]',
  TikTok: '[data-e2e=user-post-item] a[href*="/video/"]'
};
const selector = selectors[platform];
return Array.from(document.querySelectorAll(selector), a => {
    const labels = platform !== 'Facebook' ? [] : [a.innerText, a.getAttribute('aria-label'),
      ...Array.from(a.querySelectorAll('[aria-label]'), e=>e.getAttribute('aria-label'))].filter(Boolean);
    // Facebook's current Reels tiles label views with an eye icon instead of text.
    // Only accept the counter paired with that icon, never a bare likes/comment count.
    if (platform === 'Facebook' && a.querySelector('svg path[d^="M7.5 10a2.5"]') &&
        a.querySelector('svg path[d^="M3.707 5.488"]')) labels.push(a.innerText.trim() + ' views');
    return [a.href, labels];
});
"""

TT_DETAIL = """
const s = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
if (!s) return null;
try {
  const data = JSON.parse(s.textContent).__DEFAULT_SCOPE__?.['webapp.video-detail'];
  const item = data?.itemInfo?.itemStruct;
  if (String(item?.id) !== arguments[0]) return null;
  return [item.createTime, item.statsV2?.playCount ?? item.stats?.playCount ?? null];
} catch { return null; }
"""

YT_DETAIL = """
const p = window.ytInitialPlayerResponse || {};
const d = p.videoDetails || {};
if (d.videoId !== arguments[0]) return null;
const m = p.microformat?.playerMicroformatRenderer || {};
const live = m.liveBroadcastDetails || {};
if (arguments[1] === 'streams' && !live.endTimestamp) {
  if (d.isUpcoming || d.isLive || live.isLiveNow || p.playabilityStatus?.status === 'LIVE_STREAM_OFFLINE')
    return ['skip', null];
  return ['unverified', null];
}
const published = arguments[1] === 'streams' ? live.startTimestamp : null;
return [published || m.publishDate || m.uploadDate || null, d.viewCount ?? null];
"""

YT_TAB_STATE = """
const tabs = window.ytInitialData?.contents?.twoColumnBrowseResultsRenderer?.tabs;
if (!Array.isArray(tabs)) return 'loading';
const pathOf = tab => (tab?.endpoint?.commandMetadata?.webCommandMetadata?.url || '').split('?')[0].replace(/\\/$/,'');
const list = tabs.map(t=>t.tabRenderer).filter(Boolean);
const chosen = list.find(t=>t.selected);
const want = '/' + arguments[0];
if (chosen && pathOf(chosen).endsWith(want)) return 'ready';
// Only a recognized channel's tab bar can establish that this category is absent.
if (window.ytInitialData?.metadata?.channelMetadataRenderer && chosen && !list.some(t=>pathOf(t).endsWith(want)))
  return 'absent';
return 'loading';
"""

FB_DETAIL = """
// Page scripts contain multiple recommended videos. Only read the requested video's node.
const id = arguments[0];
let day = null, views = null;
for (const script of document.querySelectorAll('script[type="application/json"],script[type="application/ld+json"]')) {
  const raw = script.textContent;
  if (!raw.includes(id)) continue;
  let tree;
  try { tree = JSON.parse(raw); } catch { continue; }
  const stack = [tree];
  while (stack.length) {
    const o = stack.pop();
    if (!o || typeof o !== 'object') continue;
    if (String(o.id ?? o.video_id ?? '') === id) {
      day ??= o.publish_time || o.creation_time || o.publishDate || o.creation_story?.creation_time;
      views ??= o.video_view_count ?? o.play_count ?? o.view_count;
    }
    if (String(o.video?.id) === id) {
      day ??= o.creation_time;
      views ??= o.play_count ?? o.video_view_count ?? o.play_count_reduced;
    }
    if (o['@type'] === 'VideoObject' && [o.url,o.embedUrl,o['@id']].some(
        v=>typeof v==='string' && v.split(/[/?&#=]/).includes(id))) {
      day ??= o.uploadDate;
      const stats = [].concat(o.interactionStatistic || []);
      const plays = stats.find(s=>JSON.stringify(s.interactionType || '').includes('WatchAction'));
      views ??= plays?.userInteractionCount;
    }
    if (day && views != null) return [day,views];
    for (const v of Object.values(o)) if (v && typeof v === 'object') stack.push(v);
  }
}
return day ? [day,views ?? null] : null;
"""


FB_PROFILE = """
let rows = [], end = false;
for (const s of document.querySelectorAll('script[type="application/json"]')) {
  if (!s.textContent.includes('aggregated_fb_shorts')) continue;
  let stack;
  try { stack = [JSON.parse(s.textContent)]; } catch { continue; }
  while (stack.length) {
    const node = stack.pop();
    if (!node || typeof node !== 'object') continue;
    const feed = node.aggregated_fb_shorts;
    if (Array.isArray(feed?.edges)) {
      for (const edge of feed.edges) {
        const story = edge.profile_reel_node?.node;
        const ctx = story?.short_form_video_context;
        rows.push([story?.video?.id || ctx?.video?.id || null, story?.creation_time || null,
                   ctx?.play_count ?? ctx?.play_count_reduced ?? null]);
      }
      if (feed.page_info?.has_next_page === false) end = true;
    } else {
      for (const v of Object.values(node)) if (v && typeof v === 'object') stack.push(v);
    }
  }
}
return [rows,end];
"""


FB_OBSERVER = r"""
(() => {
  if (window.__dataviewReelsObserver) return;
  window.__dataviewReelsObserver = true;
  window.__dataviewReelsFeeds = [];
  const isGraph = value => {
    try { const u = new URL(value, location.href); return ['www.facebook.com','facebook.com'].includes(u.hostname) && u.pathname.replace(/\/$/,'') === '/api/graphql'; }
    catch { return false; }
  };
  const save = tree => {
    const stack = [tree];
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== 'object') continue;
      const feed = node.aggregated_fb_shorts;
      if (Array.isArray(feed?.edges)) {
        const rows = feed.edges.flatMap(edge => {
          const story = edge?.profile_reel_node?.node;
          const ctx = story?.short_form_video_context;
          const id = story?.video?.id || ctx?.video?.id;
          return typeof id === 'string' && /^[0-9]+$/.test(id)
            ? [[id, story?.creation_time || null, ctx?.play_count ?? ctx?.play_count_reduced ?? null]] : [];
        });
        window.__dataviewReelsFeeds.push({rows, ended: feed.page_info?.has_next_page === false});
        if (window.__dataviewReelsFeeds.length > 100) window.__dataviewReelsFeeds.shift();
      } else for (const v of Object.values(node)) if (v && typeof v === 'object') stack.push(v);
    }
  };
  const consume = text => {
    if (typeof text !== 'string' || !text.includes('aggregated_fb_shorts')) return;
    for (const line of text.replace(/^for\s*\(;;\);\s*/, '').split('\n')) {
      if (!line.trim()) continue;
      try { save(JSON.parse(line)); } catch {}
    }
  };
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    if (isGraph(url)) this.addEventListener('load', () => {
      try {
        if (this.responseType === 'json') save(this.response);
        else if (this.responseType === '' || this.responseType === 'text') consume(this.responseText);
      } catch {}
    });
    return open.call(this, method, url, ...rest);
  };
  const fetch = window.fetch;
  window.fetch = async function(...args) {
    const response = await fetch.apply(this, args);
    if (isGraph(response.url)) response.clone().text().then(consume).catch(() => {});
    return response;
  };
})();
"""


def facebook_views(value):
    exact = parse_nonnegative_int(value)
    if exact is not None:
        return exact
    return labeled_views(f"{value} views") if isinstance(value, str) else None


def facebook_feed_rows(data):
    """Read only the profile's Reels connection, excluding recommended videos."""
    rows, ended = [], False
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        feed = node.get("aggregated_fb_shorts")
        if isinstance(feed, dict) and isinstance(feed.get("edges"), list):
            for edge in feed["edges"]:
                if not isinstance(edge, dict):
                    continue
                profile_node = edge.get("profile_reel_node")
                story = profile_node.get("node") if isinstance(profile_node, dict) else None
                if not isinstance(story, dict):
                    continue
                ctx = story.get("short_form_video_context")
                ctx = ctx if isinstance(ctx, dict) else {}
                video, context_video = story.get("video"), ctx.get("video")
                key = (video.get("id") if isinstance(video, dict) else None) or (context_video.get("id") if isinstance(context_video, dict) else None)
                if isinstance(key, str) and key.isascii() and key.isdecimal():
                    raw_views = ctx.get("play_count", ctx.get("play_count_reduced"))
                    rows.append((key, story.get("creation_time"), facebook_views(raw_views)))
            ended = ended or (feed.get("page_info") or {}).get("has_next_page") is False
        else:
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    return rows, ended


class FacebookFeedCollector:
    """Capture profile pagination already requested by Chrome, without another API login."""
    def __init__(self, driver):
        self.driver = driver
        self.pending = {}
        self.failed = False
        self.ended = False

    def poll(self):
        observed = self.driver.execute_script("return (window.__dataviewReelsFeeds || []).splice(0)")
        rows = []
        if isinstance(observed, list):
            for page in observed:
                if not isinstance(page, dict):
                    continue
                self.ended = self.ended or page.get("ended") is True
                for key, created, views in page.get("rows", []):
                    if isinstance(key, str) and key.isascii() and key.isdecimal():
                        rows.append((key, created, facebook_views(views)))
        if self.driver.execute_script("return window.__dataviewReelsObserver === true") is True:
            # The page observer receives streamed GraphQL payloads whose bodies Chrome
            # does not expose through Network.getResponseBody. It is the primary source.
            self.driver.get_log("performance")
            self.pending.clear()
            return rows
        for entry in self.driver.get_log("performance"):
            try:
                message = json.loads(entry["message"])["message"]
                params = message["params"]
                url = urlsplit(params["response"]["url"])
                if message.get("method") == "Network.responseReceived" and url.hostname in {"www.facebook.com", "facebook.com"} and url.path.rstrip("/") == "/api/graphql":
                    self.pending.setdefault(params["requestId"], time.monotonic() + 12)
            except (KeyError, TypeError, ValueError):
                continue
        for request_id, deadline in list(self.pending.items()):
            try:
                response = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                body = response["body"]
                if not body:
                    if time.monotonic() < deadline:
                        continue
                    self.failed = True
                if response.get("base64Encoded"):
                    body = base64.b64decode(body).decode("utf-8")
                if "aggregated_fb_shorts" in body:
                    body = re.sub(r"^for\s*\(;;\);\s*", "", body)
                    for line in body.splitlines():
                        if not line.strip():
                            continue
                        batch, ended = facebook_feed_rows(json.loads(line))
                        rows.extend(batch)
                        self.ended = self.ended or ended
            except WebDriverException:
                if time.monotonic() < deadline:
                    continue
                self.failed = True
            except (KeyError, ValueError, UnicodeError):
                self.failed = True
            del self.pending[request_id]
        return rows


def card_ids(platform, cards, profile=None):
    found = {}
    for href, labels in cards:
        p = urlsplit(href)
        if platform == "YouTube" and p.hostname in {"www.youtube.com", "youtube.com"}:
            key = p.path[8:] if p.path.startswith("/shorts/") else parse_qs(p.query).get("v", [""])[0]
            if re.fullmatch(r"[\w-]{11}", key, re.ASCII):
                found[key] = None
        elif platform == "TikTok" and profile and href.casefold().startswith(profile.casefold() + "/video/"):
            key = p.path.rstrip("/").rsplit("/", 1)[-1]
            if key.isascii() and key.isdecimal():
                found[key] = None
        elif platform == "Facebook" and p.hostname in {"www.facebook.com", "facebook.com", "m.facebook.com"}:
            match = re.fullmatch(r"/reel/([0-9]+)/?", p.path)
            if match:
                key = match[1]
                found.setdefault(key, None)
                for label in labels:
                    for line in label.splitlines():
                        value = labeled_views(line)
                        if value is not None:
                            found[key] = value
    return found


def collect_listing(driver, platform, report, progress, check, profile=None, tab="videos"):
    listing = driver.current_window_handle
    if platform == "YouTube":
        deadline = time.monotonic() + 8
        while True:
            check()
            state = driver.execute_script(YT_TAB_STATE, tab)
            if state == "absent":
                report.complete = True
                return
            if state == "ready":
                break
            if time.monotonic() >= deadline:
                report.note = "ยืนยันแท็บของช่องไม่ได้"
                return
            time.sleep(0.4)
    driver.switch_to.new_window("tab")
    detail = driver.current_window_handle
    driver.switch_to.window(listing)
    seen = set()
    older = 0
    fb_rows = {}
    fb_end = False
    fb_collector = FacebookFeedCollector(driver) if platform == "Facebook" else None
    for batch in count():
        check()
        timeout = 75 if batch == 0 and platform == "Facebook" else 8
        deadline = time.monotonic() + timeout
        while True:
            check()
            cards = card_ids(platform, driver.execute_script(LIST_CARDS, platform, tab), profile)
            if platform == "Facebook":
                rows, fb_end = driver.execute_script(FB_PROFILE)
                rows.extend(fb_collector.poll())
                fb_end = fb_end or fb_collector.ended
                for key, day, views in rows:
                    if isinstance(key, str) and key.isascii() and key.isdecimal():
                        fb_rows[key] = (day, facebook_views(views))
                        cards.setdefault(key, None)
            fresh = [key for key in cards if key not in seen]
            if (platform == "Facebook" and fresh and time.monotonic() < deadline
                    and any(key not in fb_rows for key in fresh)):
                # Relay can render tiles a moment before response.clone().text() resolves.
                # Wait for their dates rather than opening every detail unnecessarily.
                time.sleep(0.25)
                continue
            if fresh or fb_end or time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        if not fresh:
            if fb_end:
                report.complete = not fb_collector.failed and not fb_collector.pending
            if platform == "YouTube":
                # A rendered channel grid without a continuation is the end of its list.
                report.complete = bool(driver.execute_script("""
                    const grid=document.querySelector('ytd-rich-grid-renderer');
                    const selected = window.ytInitialData?.contents?.twoColumnBrowseResultsRenderer?.tabs?.find(t=>t.tabRenderer?.selected)?.tabRenderer;
                    return !!selected?.content?.messageRenderer ||
                           !!(grid && grid.querySelector('ytd-rich-item-renderer') && !grid.querySelector('ytd-continuation-item-renderer'));
                """))
            break
        batch_days = []
        previous_cutoff = None
        if platform == "TikTok" and report.limit and len(report.videos) >= report.limit:
            previous_cutoff = report.ordered()[report.limit - 1].posted_at
        batch_times = []
        for key in fresh:
            check()
            seen.add(key)
            url = (f"https://www.youtube.com/watch?v={key}" if platform == "YouTube"
                   else f"https://www.facebook.com/reel/{key}/")
            if platform == "TikTok":
                url = f"{profile}/video/{key}"
            progress(f"{platform} • กำลังตรวจวันที่และยอดวิวคลิปที่ {len(seen):,}")
            if key in fb_rows:
                raw_day, views = fb_rows[key]
                views = views if views is not None else cards[key]
                stamp = published_time(raw_day)
                outside = report.start and stamp and not report.start <= stamp.date() <= report.end
                if stamp and (views is not None or outside):
                    report.add(url, stamp, views)
                    batch_days.append(stamp.date())
                    continue
            driver.switch_to.window(detail)
            navigate(driver, url)
            script = {"YouTube": YT_DETAIL, "Facebook": FB_DETAIL, "TikTok": TT_DETAIL}[platform]
            deadline = time.monotonic() + 4
            while True:
                check()
                pair = driver.execute_script(script, key, tab)
                if (pair and pair[0]) or time.monotonic() >= deadline:
                    break
                time.sleep(0.4)
            published, raw = pair or (None, None)
            if platform == "YouTube" and tab == "streams":
                if published == "skip":
                    continue
                if not published or published == "unverified":
                    report.missing_dates += 1
                    continue
            stamp = published_time(published)
            if key in fb_rows:
                stamp = stamp or published_time(fb_rows[key][0])
            views = facebook_views(raw) if platform == "Facebook" else parse_nonnegative_int(raw)
            report.add(url, stamp, views if views is not None else cards[key])
            if previous_cutoff is not None:
                batch_times.append(stamp)
            day = stamp.date() if stamp else None
            batch_days.append(day)
            older = older + 1 if report.start and day and day < report.start else 0
            # /videos opens YouTube's default newest-first tab. Reels can be unordered.
            if platform == "YouTube" and (older >= 3 or (report.limit and len(report.videos) >= report.limit)):
                report.complete = True
                return
        driver.switch_to.window(listing)
        if fb_end:
            report.complete = not fb_collector.failed and not fb_collector.pending
            break
        if previous_cutoff and batch_times and all(t and t < previous_cutoff for t in batch_times):
            # A complete older batch beyond the cut-off on the profile's newest-first video grid.
            report.complete = True
            break
        if report.start and platform != "YouTube" and batch > 0 and all(day and day < report.start for day in batch_days):
            # Profile grids can be reordered. Keep this early-stop result marked partial.
            break
        if report.start and batch >= 100:
            break
        driver.execute_script("window.scrollTo(0,document.documentElement.scrollHeight)")
    if not report.complete:
        report.note = {
            "Facebook": "Facebook ไม่ยืนยันว่ารายการ Reels ครบ หากมีหน้าล็อกอิน ให้เข้าสู่ระบบใน Chrome แล้วลองอีกครั้ง",
            "YouTube": "YouTube โหลดรายการไม่ครบ กรุณาตรวจสอบช่องและการเชื่อมต่อ",
            "TikTok": "TikTok แสดงเฉพาะคลิปที่โหลดได้จากหน้าโปรไฟล์",
        }[platform]


def analyze(platform, url, start, end, progress, check, *, limit=None, youtube_tabs=("videos",), driver_factory=None):
    if limit is not None and (type(limit) is not int or limit < 1 or start is not None):
        raise ValueError("จำนวนคลิปล่าสุดต้องเป็นจำนวนเต็มตั้งแต่ 1 และใช้แยกจากช่วงวัน")
    if platform == "YouTube" and (not youtube_tabs or not all(tab in YOUTUBE_TABS for tab in youtube_tabs)):
        raise ValueError("กรุณาเลือกประเภทคลิป YouTube อย่างน้อยหนึ่งประเภท")
    report = Report(start, end, limit=limit)
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    options.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
    if platform in ("TikTok", "Facebook"):
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = (driver_factory or webdriver.Chrome)(options=options)
    try:
        check()
        driver.set_page_load_timeout(30)
        if platform in ("TikTok", "Facebook"):
            driver.execute_cdp_cmd("Network.enable", {"maxTotalBufferSize": 20_000_000, "maxResourceBufferSize": 5_000_000})
        if platform == "Facebook":
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": FB_OBSERVER})
        progress(f"กำลังเปิด {platform} • หากเว็บขอให้เข้าสู่ระบบหรือยืนยันตัวตน กรุณาดำเนินการใน Chrome")
        if platform == "YouTube":
            listing = driver.current_window_handle
            report.complete = True
            notes = []
            for tab in dict.fromkeys(youtube_tabs):
                check()
                driver.switch_to.window(listing)
                navigate(driver, url.rsplit("/", 1)[0] + "/" + tab)
                part = Report(start, end, limit=limit)
                label = YOUTUBE_TABS[tab]
                try:
                    collect_listing(driver, platform, part, lambda msg: progress(f"{label} • {msg}"), check, tab=tab)
                finally:
                    for key, video in part.videos.items():
                        previous = report.videos.get(key)
                        if previous is None or (previous.views is None and video.views is not None):
                            report.videos[key] = video
                    report.missing_dates += part.missing_dates
                    report.complete = report.complete and part.complete
                if part.note:
                    notes.append(f"{label} • {part.note}")
            report.note = " / ".join(notes)
        elif platform == "TikTok":
            navigate(driver, url)
            collect_tiktok(driver, url, report, progress, check)
        else:
            navigate(driver, url)
            collect_listing(driver, platform, report, progress, check)
    except WebDriverException:
        if not report.videos:
            raise
        report.complete = False
        report.note = "การเชื่อมต่อ Chrome หยุดระหว่างเก็บข้อมูล"
    finally:
        try:
            driver.quit()
        except WebDriverException:
            pass  # A user can close the browser while a collection is finishing.
    report.select_latest()
    return report
