import base64
import binascii
import datetime
import heapq
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait


CLIP_LIMIT = 10
LOAD_TIMEOUT = 12
MAX_SCROLLS = 30
MAX_IDLE_ROUNDS = 3
BANGKOK = datetime.timezone(datetime.timedelta(hours=7))


@dataclass(frozen=True)
class Clip:
    video_id: str
    posted_at: datetime.datetime
    views: int | None


def validate_profile_url(value):
    """Accept a TikTok profile URL and discard tracking parameters."""
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in ("http", "https")
        or parsed.netloc.lower() not in ("tiktok.com", "www.tiktok.com")
        or not re.fullmatch(r"/@[A-Za-z0-9_.]+/?", parsed.path)
    ):
        raise ValueError("Enter a profile URL such as https://www.tiktok.com/@username")
    username = parsed.path.rstrip("/")[2:]
    return f"https://www.tiktok.com/@{username}", username


def parse_nonnegative_int(value):
    # Reject fractional or malformed values instead of silently changing a count.
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        return None
    return int(value)


def latest_clips(clips):
    return sorted(
        clips.values(), key=lambda clip: (clip.posted_at, int(clip.video_id)), reverse=True
    )[:CLIP_LIMIT]


class ProfileCollector:
    def __init__(self, driver, username, latest_limit=CLIP_LIMIT):
        self.driver = driver
        self.username = username.casefold()
        self.latest_limit = latest_limit
        self.clips = {}
        self.pending = {}
        self.processed = set()
        self.pages = 0
        self.exhausted = False
        self.passed_boundary = False
        self.failed_responses = 0
        self.invalid_items = set()
        self.undated = {}

    def add_page(self, data):
        if not isinstance(data, dict):
            raise ValueError("Unexpected profile response")
        if data.get("statusCode", 0) not in (0, "0"):
            raise ValueError(f"TikTok returned status {data['statusCode']}")
        items = data.get("itemList")
        if items is None and data.get("hasMore") in (False, 0, "0"):
            items = []
        if not isinstance(items, list):
            raise ValueError("Profile response has no itemList")

        cutoff = None
        if self.latest_limit and len(self.clips) >= self.latest_limit:
            cutoff = heapq.nlargest(self.latest_limit, (clip.posted_at for clip in self.clips.values()))[-1]
        new_clips = []
        for item in items:
            if not isinstance(item, dict):
                self.invalid_items.add("unknown")
                continue
            author = item.get("author") or {}
            if not isinstance(author, dict):
                self.invalid_items.add(str(item.get("id", "unknown")))
                continue
            author_name = author.get("uniqueId", "")
            if not isinstance(author_name, str) or not author_name:
                self.invalid_items.add(str(item.get("id", "unknown")))
                continue
            if author_name.casefold() != self.username:
                continue
            # Photo posts are outside the requested video-clip statistics.
            if item.get("imagePost") or item.get("imagePostInfo"):
                continue

            video_id = str(item.get("id", ""))
            views = None
            for stats in (item.get("statsV2"), item.get("stats")):
                if isinstance(stats, dict):
                    views = parse_nonnegative_int(stats.get("playCount"))
                    if views is not None:
                        break
            created = parse_nonnegative_int(item.get("createTime") or item.get("create_time"))
            try:
                if not video_id.isascii() or not video_id.isdigit() or not created:
                    raise ValueError("Missing video ID or creation time")
                posted_at = datetime.datetime.fromtimestamp(created, datetime.timezone.utc)
            except (ValueError, OverflowError, OSError):
                if video_id in self.clips:
                    continue
                if video_id.isascii() and video_id.isdigit():
                    if views is not None or video_id not in self.undated:
                        self.undated[video_id] = views
                self.invalid_items.add(video_id or "unknown")
                continue

            prior_views = self.undated.pop(video_id, None)
            if views is None:
                views = prior_views
            previous = self.clips.get(video_id)
            if previous is not None and views is None:
                views = previous.views
            clip = Clip(video_id, posted_at, views)
            if previous is None:
                new_clips.append(clip)
            self.clips[video_id] = clip
            self.invalid_items.discard(video_id)

        # Read a further page after collecting the requested count. This covers older pinned
        # clips occupying slots at the start of the newest-first profile feed.
        if cutoff is not None and new_clips:
            self.passed_boundary = all(clip.posted_at < cutoff for clip in new_clips)
        self.exhausted = data.get("hasMore") in (False, 0, "0")
        self.pages += 1

    def poll(self):
        for entry in self.driver.get_log("performance"):
            try:
                message = json.loads(entry["message"])["message"]
                if message.get("method") != "Network.responseReceived":
                    continue
                params = message["params"]
                url = urlsplit(params["response"]["url"])
                if (
                    url.hostname not in ("www.tiktok.com", "tiktok.com")
                    or url.path.rstrip("/") != "/api/post/item_list"
                ):
                    continue
                request_id = params["requestId"]
                if request_id not in self.processed:
                    self.pending.setdefault(request_id, time.monotonic() + LOAD_TIMEOUT)
            except (KeyError, TypeError, ValueError):
                continue

        # Retry bodies that arrive after responseReceived. Only mark a request
        # processed once its body has been read, or its retry deadline expires.
        for request_id, deadline in list(self.pending.items()):
            try:
                response = self.driver.execute_cdp_cmd(
                    "Network.getResponseBody", {"requestId": request_id}
                )
            except WebDriverException:
                if time.monotonic() < deadline:
                    # Preserve page order if an earlier response is still loading.
                    break
                self.failed_responses += 1
            else:
                try:
                    body = response["body"]
                    if not body and time.monotonic() < deadline:
                        break
                    if response.get("base64Encoded"):
                        body = base64.b64decode(body, validate=True).decode("utf-8")
                    self.add_page(json.loads(body))
                except (KeyError, TypeError, ValueError, binascii.Error):
                    self.failed_responses += 1
            self.processed.add(request_id)
            del self.pending[request_id]

    def wait_for_page(self):
        previous_pages = self.pages

        def page_loaded(_driver):
            self.poll()
            return self.pages > previous_pages and not self.pending

        try:
            WebDriverWait(self.driver, LOAD_TIMEOUT, poll_frequency=0.25).until(page_loaded)
        except TimeoutException:
            self.poll()

    def collect(self):
        idle_rounds = 0
        for attempt in range(MAX_SCROLLS + 1):
            previous_count = len(self.clips)
            self.wait_for_page()
            print(f"Loaded {len(self.clips)} unique clips from {self.pages} response(s).")
            if (self.exhausted or self.passed_boundary) and not self.pending:
                return True
            if len(self.clips) == previous_count:
                idle_rounds += 1
            else:
                idle_rounds = 0
            if idle_rounds >= MAX_IDLE_ROUNDS or attempt == MAX_SCROLLS:
                return False
            # Moving slightly up first also permits another scroll event when
            # the page height remains unchanged during a slow response.
            self.driver.execute_script("window.scrollBy(0, -400);")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return False


def print_results(collector, completed, profile_url):
    selected = latest_clips(collector.clips)
    print("\n=== TikTok latest 10 clips ===")
    if not selected:
        print("No video data collected. Check the profile, login or verification prompt in Chrome.")
        return

    reliable = completed and not collector.failed_responses and not collector.invalid_items
    if not reliable:
        print("WARNING: Loading was incomplete. These are the newest clips among the data collected.")
    if len(selected) < CLIP_LIMIT:
        print(f"Only {len(selected)} clips were collected (target: {CLIP_LIMIT}).")
    for index, clip in enumerate(selected, 1):
        posted = clip.posted_at.astimezone(BANGKOK).strftime("%Y-%m-%d %H:%M:%S")
        views = "unavailable" if clip.views is None else f"{clip.views:,}"
        print(f"{index:2}. {posted} (UTC+07:00) | views={views}")
        print(f"    {profile_url}/video/{clip.video_id}")

    missing = sum(clip.views is None for clip in selected)
    if missing:
        print(f"Average unavailable: {missing} selected clip(s) have missing view counts.")
    else:
        average = sum(clip.views for clip in selected) / len(selected)
        print(f"Average views ({len(selected)} clips): {average:,.2f}")
    if collector.failed_responses:
        print(f"Unreadable API responses: {collector.failed_responses}")
    if collector.invalid_items:
        print(f"Posts with incomplete identity/date data: {len(collector.invalid_items)}")


def main():
    driver = None
    try:
        target_url, username = validate_profile_url(input("TikTok Profile URL: "))
        options = webdriver.ChromeOptions()
        options.page_load_strategy = "eager"
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(45)
        driver.execute_cdp_cmd("Network.enable", {
            "maxTotalBufferSize": 20_000_000,
            "maxResourceBufferSize": 5_000_000,
        })
        print(f"Opening {target_url}")
        print("If TikTok requests login or verification, complete it in Chrome while loading.")
        try:
            driver.get(target_url)
        except TimeoutException:
            print("Page navigation timed out. Checking the responses already received.")
        collector = ProfileCollector(driver, username)
        completed = collector.collect()
        print_results(collector, completed, target_url)
    except ValueError as error:
        print(f"Invalid input: {error}")
    except WebDriverException as error:
        print(f"Chrome/TikTok error: {error.msg}")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass


if __name__ == "__main__":
    main()
