import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import MagicMock, patch
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import Cancelled, Jobs, Server, local_analyze, serialize_report, validate_input
from dataview_analysis import FB_OBSERVER, FacebookFeedCollector, LIST_CARDS, Report, card_ids, facebook_feed_rows
from tiktok10Latest import ProfileCollector

def payload(**overrides):
    return {"jobId": str(uuid.uuid4()), "platform": "TikTok", "url": "https://www.tiktok.com/@test", "mode": "latest", "amount": 2, "youtubeTabs": []} | overrides

class WorkerTests(unittest.TestCase):
    def test_facebook_pagination_reads_only_profile_connection(self):
        data = {"recommended": {"video_view_count": 99999, "id": "999"}, "data": {"aggregated_fb_shorts": {"edges": [
            {"profile_reel_node": {"node": {"creation_time": 1790208566, "video": {"id": "123"}}}},
            {"profile_reel_node": {"node": {"creation_time": 1790208565, "short_form_video_context": {"video": {"id": "124"}, "play_count_reduced": "4.9M"}}}}
        ], "page_info": {"has_next_page": False}}}}
        rows, ended = facebook_feed_rows(data)
        self.assertEqual(rows, [("123", 1790208566, None), ("124", 1790208565, 4900000)])
        self.assertTrue(ended)
        driver = MagicMock()
        driver.get_log.side_effect = [[{"message": json.dumps({"message": {"method": "Network.responseReceived", "params": {"requestId": "one", "response": {"url": "https://www.facebook.com/api/graphql/"}}}})}], []]
        driver.execute_cdp_cmd.side_effect = [{"body": ""}, {"body": "for (;;);" + json.dumps(data)}]
        collector = FacebookFeedCollector(driver)
        self.assertEqual(collector.poll(), [])
        self.assertIn("one", collector.pending)
        self.assertEqual(collector.poll(), rows)
        self.assertTrue(collector.ended)
        self.assertFalse(collector.pending)
        self.assertFalse(collector.failed)
        driver.get_log.return_value = []
        driver.get_log.side_effect = None
        driver.execute_cdp_cmd.side_effect = None
        driver.execute_cdp_cmd.return_value = {"body": ""}
        collector.pending["unreadable"] = time.monotonic() - 1
        collector.poll()
        self.assertTrue(collector.failed)

    def test_facebook_eye_icon_counter_is_not_confused_with_bare_likes(self):
        from selenium import webdriver
        from urllib.parse import quote
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        try:
            html = '<main><a href="https://www.facebook.com/reel/123/"><svg><path d="M7.5 10a2.5"></path><path d="M3.707 5.488"></path></svg>4.9 ล้าน</a><a href="https://www.facebook.com/reel/124/">200</a></main>'
            driver.get("data:text/html;charset=utf-8," + quote(html))
            cards = card_ids("Facebook", driver.execute_script(LIST_CARDS, "Facebook", "videos"))
            self.assertEqual(cards, {"123": 4900000, "124": None})
            driver.execute_script("""
              window.XMLHttpRequest = class {
                constructor() { this.listeners = {}; this.responseType = ''; }
                addEventListener(name, fn) { this.listeners[name] = fn; }
                open() {}
              };
            """)
            driver.execute_script(FB_OBSERVER)
            captured = driver.execute_script("""
              const xhr = new XMLHttpRequest();
              xhr.open('POST','https://www.facebook.com/api/graphql/');
              xhr.responseText = JSON.stringify({data:{aggregated_fb_shorts:{edges:[
                {profile_reel_node:{node:{creation_time:1790208566,video:{id:'123'}}}}
              ],page_info:{has_next_page:false}}}});
              xhr.listeners.load();
              return window.__dataviewReelsFeeds.splice(0);
            """)
            self.assertEqual(captured, [{"rows": [["123", 1790208566, None]], "ended": True}])
        finally:
            driver.quit()

    def test_manual_verification_can_resume_without_automatic_input(self):
        driver = MagicMock()
        driver.execute_script.side_effect = ["verification", None]
        messages = []
        def fake_analyze(platform, url, start, end, progress, check, *, driver_factory, **kwargs):
            driver_factory(options=MagicMock())
            check()
            return "finished"
        with patch("server.local_chrome", return_value=driver), patch("server.analyze", side_effect=fake_analyze), patch("server.time.sleep"):
            result = local_analyze("TikTok", "https://www.tiktok.com/@test", None, None, messages.append, lambda: None)
        self.assertEqual(result, "finished")
        self.assertTrue(any("กรุณาเข้าสู่ระบบ" in m for m in messages))
        self.assertTrue(any("ยืนยันตัวตนแล้ว" in m for m in messages))
        driver.find_element.assert_not_called()

    def test_waiting_for_manual_verification_is_cancellable(self):
        driver = MagicMock()
        driver.execute_script.return_value = "login"
        cancelled = threading.Event()
        def check():
            if cancelled.is_set(): raise Cancelled()
        def fake_analyze(platform, url, start, end, progress, check, *, driver_factory, **kwargs):
            driver_factory(options=MagicMock())
            check()
        with patch("server.local_chrome", return_value=driver), patch("server.analyze", side_effect=fake_analyze), patch("server.time.sleep"):
            with self.assertRaises(Cancelled):
                local_analyze("Facebook", "https://www.facebook.com/test/reels/", None, None, lambda _: cancelled.set(), check)

    def test_validation_matches_web_and_rejects_invalid_input(self):
        self.assertEqual(validate_input(payload(url="https://www.tiktok.com/@test/?lang=en"))["url"], "https://www.tiktok.com/@test")
        for amount in (0, -1, 1.2, True, "10"):
            with self.assertRaises(ValueError): validate_input(payload(amount=amount))
        with self.assertRaises(ValueError): validate_input(payload(url="https://example.com"))
        with self.assertRaises(ValueError): validate_input(payload(jobId="../health"))
        with self.assertRaises(ValueError): validate_input(payload(platform="YouTube", url="https://www.youtube.com/@test", youtubeTabs=[]))
        self.assertEqual(validate_input(payload(mode="all", amount=0))["amount"], 0)

    def test_real_engine_sorting_pinned_dates_and_unknown_views(self):
        report = Report(None, None, limit=2)
        report.add("old-pinned", "2025-01-01", 99999)
        report.add("new-pinned", "2026-11-26", 0)
        report.add("recent", "2026-11-25", None)
        report.select_latest()
        report.complete = True
        result = serialize_report(report, payload())
        self.assertEqual([v["url"] for v in result["videos"]], ["new-pinned", "recent"])
        self.assertEqual(result["knownViews"], 1)
        self.assertEqual(result["averageViews"], 0)
        self.assertFalse(result["complete"])

    def test_real_engine_dates_and_deduplication(self):
        report = Report(datetime(2026, 11, 24).date(), datetime(2026, 11, 26).date())
        report.add("outside", "2026-11-23", 900)
        report.add("same", "2026-11-25", 20)
        report.add("same", "2026-11-25", 30)
        report.add("midnight", datetime(2026, 11, 25, 17, tzinfo=__import__('datetime').timezone.utc), 0)
        self.assertEqual(len(report.videos), 2)
        self.assertEqual(report.videos["midnight"].day.isoformat(), "2026-11-26")
        self.assertEqual(report.metrics(), (2, 30, 15))

    def test_tiktok_original_collector_reads_further_page_after_pinned(self):
        collector = ProfileCollector(None, "test", 2)
        def clip(id, stamp): return {"id": str(id), "author": {"uniqueId": "test"}, "createTime": stamp, "stats": {"playCount": 10}}
        collector.add_page({"itemList": [clip(1, 1700000000), clip(2, 1795600000), clip(3, 1795500000)], "hasMore": True})
        self.assertFalse(collector.passed_boundary)
        collector.add_page({"itemList": [clip(4, 1795400000)], "hasMore": True})
        self.assertTrue(collector.passed_boundary)

    def test_job_bridge_completion_and_idempotent_creation(self):
        def analyzer(platform, url, start, end, progress, check, **kwargs):
            progress("test progress"); check()
            report = Report(start, end, limit=kwargs["limit"])
            report.add(url + "/video/1", "2026-11-26", 42)
            report.complete = True
            return report
        jobs = Jobs(analyzer)
        try:
            data = payload()
            jobs.create(data); jobs.create(data)
            for _ in range(50):
                status = jobs.snapshot(data["jobId"])
                if status["status"] == "complete": break
                time.sleep(.02)
            self.assertEqual(status["status"], "complete")
            self.assertEqual(status["result"]["totalViews"], 42)
            self.assertEqual(len(jobs.items), 1)
        finally: jobs.stop(); jobs.thread.join(1)

    def test_cancel_before_create_does_not_launch_chrome(self):
        called = []
        jobs = Jobs(lambda *a, **k: called.append(True))
        try:
            data = payload()
            jobs.cancel(data["jobId"])
            self.assertEqual(jobs.create(data)["status"], "cancelled")
            time.sleep(.05)
            self.assertEqual(called, [])
        finally: jobs.stop(); jobs.thread.join(1)

    def test_http_bridge_rejects_missing_token_and_has_no_file_access(self):
        jobs = Jobs()
        server = Server(0, "test-token", jobs)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(base + "/health")
            self.assertEqual(error.exception.code, 401)
            req = urllib.request.Request(base + "/health", headers={"Authorization": "Bearer test-token"})
            with urllib.request.urlopen(req) as response: self.assertEqual(json.load(response)["status"], "online")
            req = urllib.request.Request(base + "/../.dataview/access.token", headers={"Authorization": "Bearer test-token"})
            with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(req)
            self.assertEqual(error.exception.code, 404)
        finally: server.shutdown(); server.server_close(); jobs.stop(); jobs.thread.join(1)

if __name__ == "__main__": unittest.main()
