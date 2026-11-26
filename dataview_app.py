import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from selenium.common.exceptions import WebDriverException

from dataview_analysis import EXAMPLES, PLATFORMS, YOUTUBE_TABS, analyze, date_window, profile_url


class Cancelled(Exception):
    pass


class Dashboard:
    def __init__(self, root):
        self.root = root
        root.title("DataView • วิเคราะห์ยอดวิว")
        root.geometry("850x650")
        root.minsize(680, 550)
        root.configure(bg="#f1f5f8")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 11), background="#f1f5f8", foreground="#183747")
        style.configure("TEntry", fieldbackground="white", padding=5)
        style.configure("TCombobox", padding=5)
        style.configure("Run.TButton", background="#006f72", foreground="white", padding=(14, 7))
        style.map("Run.TButton", background=[("active", "#005c61"), ("disabled", "#597378")])
        style.configure("Treeview", rowheight=29, fieldbackground="white", background="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=5)
        self.messages = queue.Queue()
        self.cancel = threading.Event()
        self.busy = self.closing = False
        self.platform = tk.StringVar(value=PLATFORMS[0])
        self.url = tk.StringVar()
        self.days = tk.StringVar(value="30")
        self.clips = tk.StringVar(value="10")
        self.mode = tk.StringVar(value="ย้อนหลังตามวัน")
        self.tab_vars = {tab: tk.BooleanVar(value=tab == "videos") for tab in YOUTUBE_TABS}
        self.status = tk.StringVar(value="เลือกแพลตฟอร์ม ใส่ลิงก์ แล้วเลือกคลิปที่ต้องการวิเคราะห์")
        self.period = tk.StringVar(value="ยอดวิวสะสม ณ เวลาที่อ่าน")
        self.example = tk.StringVar(value=EXAMPLES[self.platform.get()])

        header = tk.Frame(root, bg="#123b49", padx=22, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="DataView", font=("Segoe UI", 21, "bold"), fg="white", bg="#123b49").pack(side="left")
        tk.Label(header, text="วิเคราะห์ยอดวิว", font=("Segoe UI", 13), fg="#cde9e9", bg="#123b49", padx=14).pack(side="left")
        body = ttk.Frame(root, padding=(20, 12))
        body.pack(fill="both", expand=True)
        form = ttk.Frame(body)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        for col, title in enumerate(("แพลตฟอร์ม", "ลิงก์ช่องหรือโปรไฟล์")):
            ttk.Label(form, text=title).grid(row=0, column=col, sticky="w")
        self.platform_box = ttk.Combobox(form, textvariable=self.platform, values=PLATFORMS, width=10, state="readonly")
        self.platform_box.grid(row=1, column=0, padx=(0, 10))
        self.platform_box.bind("<<ComboboxSelected>>", self.update_form)
        self.url_entry = ttk.Entry(form, textvariable=self.url)
        self.url_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        self.url_entry.grid_configure(columnspan=2)
        ttk.Label(form, textvariable=self.example, foreground="#48616c", font=("Segoe UI", 9)).grid(row=2, column=1, sticky="w")
        options = ttk.Frame(form)
        options.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(options, text="เลือกคลิป").pack(side="left", padx=(0, 8))
        self.mode_box = ttk.Combobox(options, textvariable=self.mode, state="readonly", width=16,
                                     values=("ย้อนหลังตามวัน", "คลิปล่าสุด", "ทั้งหมดของช่อง"))
        self.mode_box.pack(side="left")
        self.mode_box.bind("<<ComboboxSelected>>", self.update_form)
        self.days_entry = ttk.Entry(options, textvariable=self.days, width=7)
        self.days_entry.pack(side="left", padx=8)
        self.unit = ttk.Label(options, text="วัน รวมวันนี้")
        self.unit.pack(side="left")
        self.tab_frame = ttk.Frame(form)
        self.tab_frame.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(self.tab_frame, text="ประเภท YouTube").pack(side="left", padx=(0, 6))
        self.tab_buttons = []
        for tab, label in YOUTUBE_TABS.items():
            box = ttk.Checkbutton(self.tab_frame, text=label, variable=self.tab_vars[tab])
            box.pack(side="left", padx=4)
            self.tab_buttons.append(box)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 4))
        self.run_button = ttk.Button(actions, text="เริ่มวิเคราะห์", style="Run.TButton", command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="ยกเลิก", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.bar = ttk.Progressbar(actions, mode="indeterminate", length=100)
        self.status_label = ttk.Label(body, textvariable=self.status, wraplength=740)
        self.status_label.pack(fill="x", pady=(2, 10))
        ttk.Separator(body).pack(fill="x")
        ttk.Label(body, text="ผลการวิเคราะห์", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(10, 0))
        ttk.Label(body, textvariable=self.period, wraplength=740).pack(anchor="w")
        cards = tk.Frame(body, bg="#f1f5f8")
        cards.pack(fill="x", pady=10)
        self.metrics = []
        for index, title in enumerate(("จำนวนคลิปที่เลือกได้", "ยอดวิวรวมที่อ่านได้", "ยอดวิวเฉลี่ยต่อคลิปที่มีข้อมูล")):
            cards.columnconfigure(index, weight=1, uniform="metric")
            card = tk.Frame(cards, bg="white", padx=10, pady=6)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0))
            tk.Label(card, text=title, font=("Segoe UI", 10), bg="white", fg="#48616c").pack(anchor="w")
            value = tk.StringVar(value="—")
            tk.Label(card, textvariable=value, font=("Segoe UI", 17, "bold"), fg="#006f72", bg="white").pack(anchor="w")
            self.metrics.append(value)
        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table, columns=("day", "views", "url"), height=5, show="headings", selectmode="browse")
        for key, title, width, anchor in (("day", "วันที่เผยแพร่", 110, "center"), ("views", "ยอดวิว", 105, "e"), ("url", "ลิงก์คลิป", 420, "w")):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=80, anchor=anchor, stretch=key == "url")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<Double-1>", self.open_video)
        self.table.bind("<Return>", self.open_video)
        ttk.Label(body, text="ดับเบิลคลิกแถวเพื่อเปิดคลิป", font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.url_entry.focus_set()

    def open_video(self, event):
        row = self.table.identify_row(event.y) if event.keysym != "Return" else self.table.focus()
        if row:
            webbrowser.open(self.table.set(row, "url"))

    def update_form(self, event=None):
        self.example.set(EXAMPLES[self.platform.get()])
        if self.platform.get() == "YouTube":
            self.tab_frame.grid()
        else:
            self.tab_frame.grid_remove()
        if self.mode.get() == "ทั้งหมดของช่อง":
            self.unit.pack_forget()
            self.days_entry.pack_forget()
        else:
            latest = self.mode.get() == "คลิปล่าสุด"
            self.days_entry.configure(textvariable=self.clips if latest else self.days)
            self.unit.configure(text="คลิป" if latest else "วัน รวมวันนี้")
            self.days_entry.pack(side="left", padx=8)
            self.unit.pack(side="left")

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.run_button.configure(state=state)
        self.url_entry.configure(state=state)
        self.days_entry.configure(state=state)
        self.platform_box.configure(state="disabled" if busy else "readonly")
        self.mode_box.configure(state="disabled" if busy else "readonly")
        for button in self.tab_buttons:
            button.configure(state=state)
        self.stop_button.configure(state="normal" if busy else "disabled")
        if busy:
            self.bar.pack(side="left", padx=6)
            self.bar.start()
        else:
            self.bar.stop()
            self.bar.pack_forget()

    def start(self):
        if self.busy:
            return
        platform = self.platform.get()
        mode = self.mode.get()
        start = end = limit = None
        tabs = tuple(tab for tab, var in self.tab_vars.items() if var.get())
        try:
            url = profile_url(platform, self.url.get())
            if platform == "YouTube" and not tabs:
                raise ValueError("กรุณาเลือกประเภทคลิป YouTube อย่างน้อยหนึ่งประเภท")
            if mode == "ย้อนหลังตามวัน":
                start, end = date_window(self.days.get())
                scope = f"คลิปที่เผยแพร่ {start:%d/%m/%Y} – {end:%d/%m/%Y} ตามเวลาไทย"
            elif mode == "คลิปล่าสุด":
                value = self.clips.get().strip()
                if not value.isdecimal() or len(value) > 18 or int(value) < 1:
                    raise ValueError("กรุณาระบุจำนวนคลิปล่าสุดเป็นจำนวนเต็มตั้งแต่ 1")
                limit = int(value)
                scope = f"{limit:,} คลิปล่าสุด"
            else:
                scope = "คลิปสาธารณะทั้งหมดของช่อง"
        except ValueError as error:
            self.status.set(str(error))
            return
        self.table.delete(*self.table.get_children())
        for metric in self.metrics:
            metric.set("—")
        rounding = " (Facebook อาจปัดเศษ)" if platform == "Facebook" else ""
        categories = " / ".join(YOUTUBE_TABS[t] for t in tabs) if platform == "YouTube" else ""
        self.period.set(f"{platform} {categories}  •  {url}\n{scope}  •  ยอดวิวสะสม ณ เวลาที่อ่าน{rounding}")
        self.status.set("กำลังเปิด Chrome…")
        self.cancel.clear()
        self.set_busy(True)
        threading.Thread(target=self.worker, args=(platform, url, start, end, limit, tabs), daemon=True).start()
        self.root.after(100, self.poll)

    def worker(self, platform, url, start, end, limit, tabs):
        def check():
            if self.cancel.is_set():
                raise Cancelled()
        try:
            report = analyze(platform, url, start, end, lambda s: self.messages.put(("progress", s)), check,
                             limit=limit, youtube_tabs=tabs)
            check()
            self.messages.put(("done", report))
        except Cancelled:
            self.messages.put(("error", "ยกเลิกการวิเคราะห์แล้ว"))
        except WebDriverException as error:
            detail = (error.msg or type(error).__name__).splitlines()[0]
            self.messages.put(("error", "อ่านข้อมูลไม่ได้ กรุณาตรวจสอบ Chrome และอินเทอร์เน็ต • " + detail))
        except Exception as error:
            self.messages.put(("error", f"วิเคราะห์ไม่สำเร็จ • {error}"))

    def poll(self):
        while not self.messages.empty():
            kind, value = self.messages.get_nowait()
            if kind == "progress":
                if not self.cancel.is_set():
                    self.status.set(value)
            else:
                self.set_busy(False)
                if self.closing:
                    self.root.destroy()
                    return
                if kind == "done":
                    self.show(value)
                else:
                    self.status.set(value)
                return
        if self.busy:
            self.root.after(100, self.poll)

    def show(self, report):
        count, total, mean = report.metrics()
        n = len(report.videos)
        partial = not report.complete or report.missing_dates or count < n
        if n or not partial:
            self.metrics[0].set(f"{n:,}")
        if count or (not partial and not n):
            self.metrics[1].set(f"{total:,}")
        if mean is not None:
            self.metrics[2].set(f"{mean:,.2f}")
        for video in report.ordered():
            self.table.insert("", "end", values=(video.day.strftime("%d/%m/%Y") if video.day else "ไม่มีข้อมูล",
                              f"{video.views:,}" if video.views is not None else "ไม่มีข้อมูล", video.url))
        if not partial and not n:
            self.status.set("วิเคราะห์เสร็จแล้ว • ไม่พบคลิปตามเงื่อนไขที่เลือก")
            return
        parts = ["ข้อมูลบางส่วน" if partial else "วิเคราะห์เสร็จแล้ว"]
        if not n and partial:
            parts.append("ยังยืนยันจำนวนคลิปตามเงื่อนไขไม่ได้")
        if report.limit is not None:
            parts.append(f"เลือกได้ {n:,} จากที่ขอ {report.limit:,} คลิป")
            if not report.complete or report.missing_dates:
                parts.append("เรียงจากคลิปที่ยืนยันเวลาเผยแพร่ได้")
        if report.note:
            parts.append(report.note)
        if report.missing_dates:
            parts.append(f"ข้าม {report.missing_dates:,} รายการที่ยืนยันข้อมูลเผยแพร่ไม่ได้")
        if count < n:
            parts.append(f"คำนวณยอดวิวจาก {count:,} ใน {n:,} คลิป")
        self.status.set(" • ".join(parts))

    def stop(self):
        self.cancel.set()
        self.stop_button.configure(state="disabled")
        self.status.set("กำลังยกเลิกและปิด Chrome ที่ใช้วิเคราะห์…")

    def close(self):
        if self.busy:
            self.closing = True
            self.stop()
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()
