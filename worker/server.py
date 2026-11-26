"""Authenticated local bridge to the existing DataView analysis engine."""
from __future__ import annotations

import hmac
import json
import os
import queue
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dataview_analysis import PLATFORMS, YOUTUBE_TABS, analyze, date_window, profile_url
from selenium import webdriver

STATE = ROOT / ".dataview"


class Cancelled(Exception):
    pass


def local_chrome(*, options):
    options.add_argument("--user-data-dir=" + str(STATE / "chrome-profile"))
    options.add_argument("--no-first-run")
    return webdriver.Chrome(options=options)


def local_analyze(*args, **kwargs):
    progress, check = args[4], args[5]
    driver = None
    next_probe = 0

    def factory(**options):
        nonlocal driver
        driver = local_chrome(**options)
        return driver

    def check_with_verification():
        nonlocal next_probe
        check()
        if driver is None or time.monotonic() < next_probe:
            return
        next_probe = time.monotonic() + 1
        until = time.monotonic() + 600
        waiting = False
        while True:
            check()
            reason = driver.execute_script(r"""
              const visible = el => !!el && !!(el.offsetWidth || el.offsetHeight) && getComputedStyle(el).visibility !== 'hidden';
              if (/^\/(two_step_verification|checkpoint)(\/|$)/.test(location.pathname) ||
                  [...document.querySelectorAll('[id*=captcha], [class*=captcha]')].some(visible) ||
                  /sign in to confirm you.re not a bot/i.test(document.body?.innerText || '')) return 'verification';
              return [...document.querySelectorAll('input[type=password]')].some(visible) ? 'login' : null;
            """)
            if not reason:
                if waiting: progress("ยืนยันตัวตนแล้ว กำลังอ่านข้อมูลต่อ…")
                return
            if not waiting:
                progress("กรุณาเข้าสู่ระบบหรือยืนยันตัวตนในหน้าต่าง Chrome ของ DataView บนเครื่อง (รอได้สูงสุด 10 นาที)")
            waiting = True
            if time.monotonic() >= until:
                raise ValueError("หมดเวลารอการยืนยันตัวตนใน Chrome กรุณาลองวิเคราะห์ใหม่")
            time.sleep(1)

    arguments = list(args)
    arguments[5] = check_with_verification
    return analyze(*arguments, **kwargs, driver_factory=factory)


def validate_input(raw):
    if not isinstance(raw, dict):
        raise ValueError("ข้อมูลคำขอไม่ถูกต้อง")
    job_id = raw.get("jobId")
    try:
        parsed = uuid.UUID(job_id)
        if parsed.version != 4 or str(parsed) != job_id.lower():
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("รหัสงานไม่ถูกต้อง") from None
    platform, mode, amount = raw.get("platform"), raw.get("mode"), raw.get("amount")
    if platform not in PLATFORMS or mode not in ("days", "latest", "all"):
        raise ValueError("แพลตฟอร์มหรือรูปแบบการวิเคราะห์ไม่ถูกต้อง")
    if not isinstance(raw.get("url"), str) or len(raw["url"]) > 2048:
        raise ValueError("ลิงก์ช่องหรือโปรไฟล์ไม่ถูกต้อง")
    if mode != "all" and (type(amount) is not int or amount < 1 or amount > 2**53 - 1):
        raise ValueError("จำนวนวันหรือจำนวนคลิปต้องเป็นจำนวนเต็มตั้งแต่ 1")
    if mode == "days":
        date_window(amount)
    tabs = raw.get("youtubeTabs", [])
    if platform == "YouTube" and (not isinstance(tabs, list) or not tabs or any(not isinstance(t, str) or t not in YOUTUBE_TABS for t in tabs)):
        raise ValueError("กรุณาเลือกประเภทคลิป YouTube อย่างน้อยหนึ่งประเภท")
    return {"jobId": job_id.lower(), "platform": platform, "url": profile_url(platform, raw["url"]), "mode": mode,
            "amount": 0 if mode == "all" else amount, "youtubeTabs": list(dict.fromkeys(tabs)) if platform == "YouTube" else []}


def serialize_report(report, data):
    videos = [{"url": v.url, "publishedAt": v.posted_at.isoformat() if v.posted_at else None,
               "day": v.day.isoformat() if v.day else None, "views": v.views} for v in report.ordered()]
    known, total, average = report.metrics()
    return {k: v for k, v in data.items() if k != "jobId"} | {
        "start": report.start.isoformat() if report.start else None,
        "end": report.end.isoformat() if report.end else None,
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        "complete": bool(report.complete and not report.missing_dates and known == len(videos)),
        "notes": [report.note] if report.note else [], "videos": videos,
        "missingDates": report.missing_dates, "knownViews": known, "totalViews": total, "averageViews": average}


class Jobs:
    def __init__(self, analyzer=local_analyze):
        self.analyzer = analyzer
        self.lock = threading.RLock()
        self.items = {}
        self.pending = queue.Queue()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="dataview-analysis")
        self.thread.start()

    def prune(self):
        now = time.monotonic()
        for key, item in list(self.items.items()):
            if item["status"] in ("complete", "error", "cancelled") and now - item["updated"] > 3600:
                del self.items[key]

    def create(self, raw):
        data = validate_input(raw)
        with self.lock:
            self.prune()
            job_id = data["jobId"]
            if job_id in self.items:
                item = self.items[job_id]
                if item["input"] is not None and item["input"] != data:
                    raise ValueError("รหัสงานซ้ำกับคำขออื่น")
                return self.snapshot(job_id)
            if sum(j["status"] in ("queued", "running") for j in self.items.values()) >= 8:
                raise OverflowError("มีงานรออยู่หลายรายการ กรุณารอให้งานเดิมเสร็จก่อน")
            now = time.monotonic()
            self.items[job_id] = {"input": data, "status": "queued", "message": "กำลังรอเครื่องดึงข้อมูล", "result": None,
                                  "cancel": threading.Event(), "updated": now, "last_seen": now}
            self.pending.put(job_id)
            return self.snapshot(job_id)

    def snapshot(self, job_id):
        with self.lock:
            item = self.items[job_id]
            item["last_seen"] = time.monotonic()
            return {"jobId": job_id, "status": item["status"], "message": item["message"], "result": item["result"]}

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.items:
                # A cancellation can reach the worker before the create request.
                now = time.monotonic()
                self.prune()
                if len(self.items) >= 128:
                    raise OverflowError("มีคำขอมากเกินไป กรุณารอสักครู่")
                self.items[job_id] = {"input": None, "status": "cancelled", "message": "ยกเลิกการวิเคราะห์แล้ว", "result": None,
                                      "cancel": threading.Event(), "updated": now, "last_seen": now}
            item = self.items[job_id]
            if item["status"] in ("running", "queued", "cancelled"):
                item["cancel"].set()
                item["status"] = "cancelled"
                item["message"] = "ยกเลิกการวิเคราะห์แล้ว"
                item["updated"] = time.monotonic()
            return self.snapshot(job_id)

    def run(self):
        while not self.stopping.is_set():
            try:
                job_id = self.pending.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.lock:
                item = self.items.get(job_id)
                if not item or item["cancel"].is_set():
                    continue
                item["status"] = "running"
                data = item["input"]

            def check():
                if item["cancel"].is_set() or self.stopping.is_set() or time.monotonic() - item["last_seen"] > 600:
                    raise Cancelled()

            def progress(message):
                check()
                with self.lock:
                    item["message"] = message
                    item["updated"] = time.monotonic()

            try:
                start, end = date_window(data["amount"]) if data["mode"] == "days" else (None, None)
                report = self.analyzer(data["platform"], data["url"], start, end, progress, check,
                                       limit=data["amount"] if data["mode"] == "latest" else None,
                                       youtube_tabs=tuple(data["youtubeTabs"]))
                check()
                result = serialize_report(report, data)
                if not result["videos"] and not report.complete:
                    raise ValueError(report.note or "ไม่พบข้อมูลคลิปที่อ่านได้ กรุณาตรวจสอบหน้าต่าง Chrome แล้วลองอีกครั้ง")
                with self.lock:
                    item["result"] = result
                    item["status"] = "complete"
                    item["message"] = "วิเคราะห์เสร็จแล้ว"
            except Cancelled:
                with self.lock:
                    item["status"], item["message"] = "cancelled", "ยกเลิกการวิเคราะห์แล้ว"
            except Exception as error:
                with self.lock:
                    item["status"] = "error"
                    item["message"] = str(error) if isinstance(error, ValueError) else "อ่านข้อมูลไม่สำเร็จ กรุณาตรวจสอบ Chrome การเข้าสู่ระบบ และอินเทอร์เน็ตแล้วลองอีกครั้ง"
                print(f"DataView job {job_id}: {type(error).__name__}", flush=True)
            finally:
                with self.lock:
                    item["updated"] = time.monotonic()

    def stop(self):
        self.stopping.set()
        with self.lock:
            for item in self.items.values():
                item["cancel"].set()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, port, token, jobs=None):
        self.token, self.jobs = token, jobs or Jobs()
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    server: Server
    def log_message(self, *_):
        pass

    def send(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def dispatch(self, method):
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.token):
            self.send({"error": "รหัสเชื่อมต่อไม่ถูกต้อง"}, 401)
            return
        try:
            if self.path == "/health" and method == "GET":
                self.send({"status": "online", "name": "DataView local worker", "pid": os.getpid()})
            elif self.path == "/jobs" and method == "POST":
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 4096:
                    raise ValueError("ขนาดคำขอไม่ถูกต้อง")
                self.connection.settimeout(10)
                self.send(self.server.jobs.create(json.loads(self.rfile.read(length))), 202)
            elif re.fullmatch(r"/jobs/[0-9a-f-]{36}", self.path):
                job_id = self.path.split("/")[-1]
                if method == "GET":
                    self.send(self.server.jobs.snapshot(job_id))
                elif method == "DELETE":
                    self.send(self.server.jobs.cancel(job_id))
                else:
                    self.send({"error": "ไม่รองรับคำขอนี้"}, 405)
            elif self.path == "/shutdown" and method == "POST":
                self.server.jobs.stop()
                self.send({"status": "stopping"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.send({"error": "ไม่พบคำขอนี้"}, 404)
        except KeyError:
            self.send({"error": "ไม่พบงานนี้ งานอาจหมดอายุหรือเครื่องดึงข้อมูลถูกเปิดใหม่"}, 404)
        except OverflowError as error:
            self.send({"error": str(error)}, 429)
        except (ValueError, TypeError, TimeoutError):
            self.send({"error": "ข้อมูลคำขอไม่ถูกต้อง"}, 400)

    def do_GET(self): self.dispatch("GET")
    def do_POST(self): self.dispatch("POST")
    def do_DELETE(self): self.dispatch("DELETE")


if __name__ == "__main__":
    token = (STATE / "access.token").read_text().strip()
    server = Server(8765, token)
    print("DataView local worker listening on 127.0.0.1:8765", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.jobs.stop()
        server.jobs.thread.join(timeout=35)
        server.server_close()
