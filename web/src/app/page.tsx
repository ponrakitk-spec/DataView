"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { examples, platforms, youtubeTabs, type AnalysisInput, type AnalysisResult, type Mode, type Platform, type YoutubeTab } from "@/lib/analysis";

function Icon({ name, size = 20 }: { name: "chart" | "grid" | "link" | "play" | "eye" | "average" | "clock" | "check" | "info" | "stop"; size?: number }) {
  const shapes: Record<string, ReactNode> = {
    chart: <><path d="M5 19v-6m7 6V5m7 14v-9" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    link: <><path d="m10 13 4-4M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 1 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 0)" /></>,
    play: <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m10 9 5 3-5 3z" /></>,
    eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
    average: <><path d="M4 19h16M6 14V9m6 5V5m6 9v-3M4 17h16" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5m0-9h.01" /></>,
    stop: <rect x="6" y="6" width="12" height="12" rx="1" />,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>;
}

function PlatformMark({ platform, small = false }: { platform: Platform; small?: boolean }) {
  return <span className={`platform-mark ${platform.toLowerCase()} ${small ? "small" : ""}`} aria-hidden="true">{platform === "YouTube" ? <svg viewBox="0 0 24 24" fill="currentColor"><path d="M21.6 7.2a3 3 0 0 0-2.1-2.1C17.6 4.6 12 4.6 12 4.6s-5.6 0-7.5.5a3 3 0 0 0-2.1 2.1 31 31 0 0 0-.5 4.8 31 31 0 0 0 .5 4.8 3 3 0 0 0 2.1 2.1c1.9.5 7.5.5 7.5.5s5.6 0 7.5-.5a3 3 0 0 0 2.1-2.1 31 31 0 0 0 .5-4.8 31 31 0 0 0-.5-4.8ZM10 15.2V8.8l5.5 3.2Z" /></svg> : platform === "Facebook" ? <svg viewBox="0 0 24 24" fill="currentColor"><path d="M14 22V13h3l.5-4H14V7c0-1.2.3-2 2-2h2V1.4C17.2 1.2 16 1 14.6 1 11.2 1 9 3 9 6.6V9H6v4h3v9Z" /></svg> : <svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.6 2c.4 2.6 1.9 4.2 4.4 4.4v3.4a10 10 0 0 1-4.5-1.2V16a6 6 0 1 1-5.2-5.9v3.5a2.6 2.6 0 1 0 1.7 2.5V2Z" /></svg>}</span>;
}
const number = (value: number | null | undefined, decimals = 0) => value == null ? "—" : new Intl.NumberFormat("th-TH", { maximumFractionDigits: decimals, minimumFractionDigits: decimals }).format(value);
const dateText = (value: string) => new Intl.DateTimeFormat("th-TH", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Bangkok" }).format(new Date(value));
const scopeText = (v: Pick<AnalysisInput, "mode" | "amount">) => v.mode === "all" ? "ทั้งหมดของช่อง" : v.mode === "latest" ? `${number(v.amount)} คลิปล่าสุด` : `ย้อนหลัง ${number(v.amount)} วัน รวมวันนี้`;

export default function Home() {
  const [platform, setPlatform] = useState<Platform>("YouTube");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<Mode>("latest");
  const [days, setDays] = useState("30");
  const [clips, setClips] = useState("10");
  const [tabs, setTabs] = useState<YoutubeTab[]>(["videos"]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [workerUrl, setWorkerUrl] = useState("");
  const [workerKey, setWorkerKey] = useState("");
  const [workerState, setWorkerState] = useState<"unset" | "checking" | "online" | "offline">("unset");
  const [connectionError, setConnectionError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLElement | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => { if (!busy) return; const timer = setInterval(() => setSeconds(s => s + 1), 1000); return () => clearInterval(timer); }, [busy]);
  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const worker = fragment.get("worker"), key = fragment.get("key");
    if (worker && key) {
      setWorkerUrl(worker); setWorkerKey(key);
      sessionStorage.setItem("dataview-connection", JSON.stringify({ worker, key }));
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    } else {
      try { const saved = JSON.parse(sessionStorage.getItem("dataview-connection") || "null"); if (saved) { setWorkerUrl(saved.worker); setWorkerKey(saved.key); } } catch { /* no saved connection */ }
    }
  }, []);
  useEffect(() => {
    if (!workerUrl || !workerKey) { setWorkerState("unset"); return; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setWorkerState("checking"); setConnectionError("");
      try {
        const response = await fetch("/api/worker", { headers: { "X-DataView-Worker": workerUrl.trim(), Authorization: `Bearer ${workerKey.trim()}` }, signal: controller.signal });
        const data = await response.json();
        if (!response.ok || data.status !== "online") throw new Error(data.error || "ติดต่อเครื่องดึงข้อมูลไม่ได้");
        sessionStorage.setItem("dataview-connection", JSON.stringify({ worker: workerUrl.trim(), key: workerKey.trim() }));
        setWorkerState("online");
      } catch (error) { if (!controller.signal.aborted) { setWorkerState("offline"); setConnectionError(error instanceof Error ? error.message : "ติดต่อเครื่องดึงข้อมูลไม่ได้"); } }
    }, 500);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [workerUrl, workerKey]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!workerUrl || !workerKey) { setError("กรุณาเปิด Start-DataView.ps1 บนเครื่องดึงข้อมูล แล้วใช้หน้าเว็บที่ตัวเปิดเปิดให้"); return; }
    if (platform === "YouTube" && !tabs.length) { setError("กรุณาเลือกประเภทคลิป YouTube อย่างน้อยหนึ่งประเภท"); return; }
    const amount = mode === "all" ? 0 : Number(mode === "days" ? days : clips);
    if (mode !== "all" && (!Number.isSafeInteger(amount) || amount < 1)) { setError("จำนวนวันหรือจำนวนคลิปต้องเป็นจำนวนเต็มตั้งแต่ 1"); return; }
    const controller = new AbortController();
    const jobId = crypto.randomUUID();
    const headers = { "Content-Type": "application/json", "X-DataView-Worker": workerUrl.trim(), Authorization: `Bearer ${workerKey.trim()}` };
    abortRef.current = controller;
    setBusy(true); setError(""); setResult(null); setSeconds(0); setStatus("กำลังเริ่มวิเคราะห์…");
    let finished = false;
    try {
      const response = await fetch("/api/analyze", { method: "POST", headers, body: JSON.stringify({ platform, url, mode, amount, youtubeTabs: tabs, jobId }), signal: controller.signal });
      if (!response.ok) { const data = await response.json(); throw new Error(data.error || "ส่งคำขอไม่สำเร็จ"); }
      let failures = 0;
      while (true) {
        if (controller.signal.aborted) throw new DOMException("Cancelled", "AbortError");
        let data;
        try {
          const poll = await fetch(`/api/analyze/${jobId}`, { headers, signal: controller.signal, cache: "no-store" });
          data = await poll.json();
          if (!poll.ok) throw new Error(data.error || "อ่านสถานะงานไม่สำเร็จ");
          failures = 0;
        } catch (error) {
          if (controller.signal.aborted || ++failures >= 3) throw error;
          setStatus("กำลังเชื่อมต่อเครื่องดึงข้อมูลอีกครั้ง…");
          await new Promise(resolve => setTimeout(resolve, 1500));
          continue;
        }
        setStatus(data.message || "กำลังวิเคราะห์…");
        if (data.status === "error") throw new Error(data.message);
        if (data.status === "cancelled") { setStatus("ยกเลิกการวิเคราะห์แล้ว"); break; }
        if (data.status === "complete") { finished = true; setResult(data.result); setStatus("วิเคราะห์เสร็จแล้ว"); break; }
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
    } catch (err) {
      const cancelled = controller.signal.aborted;
      if (cancelled) setStatus("กำลังส่งคำขอยกเลิกไปยังเครื่องดึงข้อมูล…");
      else { setError(err instanceof Error ? err.message : "วิเคราะห์ไม่สำเร็จ"); setStatus(""); }
      try {
        const stop = await fetch(`/api/analyze/${jobId}`, { method: "DELETE", headers, keepalive: true });
        if (!stop.ok) throw new Error();
        if (cancelled) setStatus("ยกเลิกการวิเคราะห์แล้ว");
      } catch { if (cancelled) { setStatus(""); setError("ติดต่อเครื่องเพื่อยกเลิกไม่ได้ กรุณาปิดหน้าต่าง Chrome ของงานนี้บนเครื่องดึงข้อมูล"); } }
    } finally {
      abortRef.current = null; setBusy(false);
      if (finished) setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a href="/" className="brand" aria-label="DataView หน้าหลัก"><span className="brand-symbol"><Icon name="chart" size={27} /></span><span>DataView<span className="brand-caption">By Cheese Ponrakit</span></span></a>
      <div className="nav-label">WORKSPACE</div>
      <div className="nav-active"><Icon name="grid" /><span>ภาพรวมการวิเคราะห์</span><span className="nav-dot" /></div>
      <div className="sidebar-platforms"><span className="nav-label">แพลตฟอร์มที่รองรับ</span>{platforms.map(p => <div key={p}><PlatformMark platform={p} small /><span>{p === "Facebook" ? "Facebook Reels" : p}</span></div>)}</div>
      <div className="sidebar-bottom"><div className="avatar">CP</div><div><strong>Cheese Ponrakit</strong><span>ผู้พัฒนา DataView</span></div></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><span className="breadcrumb">Workspace <span>/</span> <strong>ภาพรวมการวิเคราะห์</strong></span><span className="topbar-note"><Icon name="clock" size={16} /> เวลาไทย (UTC+07)</span></header>
      <main>
        <div className="page-heading"><div><span className="eyebrow">YOUR CONTENT, IN FOCUS</span><h1>ทุกยอดวิว ในมุมมองเดียว<span>.</span></h1><p>วิเคราะห์วิดีโอจากช่องที่คุณสนใจ ด้วยข้อมูลจริงจาก 3 แพลตฟอร์ม</p></div><div className="heading-art" aria-hidden="true"><span /><span /><span /><span /><span /></div></div>

        <section className="analysis-panel" aria-labelledby="analysis-title">
          <div className="section-heading"><div className="section-title"><span className="section-icon"><Icon name="link" /></span><div><h2 id="analysis-title">เริ่มวิเคราะห์ช่อง</h2><p>เลือกแพลตฟอร์มและวางลิงก์ช่องหรือโปรไฟล์</p></div></div><span className="pill">ข้อมูลสาธารณะ</span></div>
          <details className="connection-panel" open={!workerUrl || !workerKey}>
            <summary><span className={`worker-indicator ${workerState}`} />เครื่องดึงข้อมูล: {workerState === "online" ? "เชื่อมต่อแล้ว" : workerState === "checking" ? "กำลังตรวจสอบ…" : workerState === "offline" ? "ออฟไลน์" : "ยังไม่เชื่อมต่อ"}<span>ตั้งค่าการเชื่อมต่อ</span></summary>
            <div className="connection-fields"><p>เปิด <strong>Start-DataView.ps1</strong> บนเครื่องของคุณ เว็บที่เปิดขึ้นจะเชื่อมต่อเครื่องให้อัตโนมัติ หรือกรอกข้อมูลจากไฟล์ .dataview/connection.json</p><label htmlFor="worker-url">ลิงก์เครื่องดึงข้อมูล</label><input id="worker-url" type="url" value={workerUrl} onChange={e => setWorkerUrl(e.target.value)} placeholder="https://…trycloudflare.com" disabled={busy} autoComplete="off" /><label htmlFor="worker-key">รหัสเชื่อมต่อ</label><input id="worker-key" type="password" value={workerKey} onChange={e => setWorkerKey(e.target.value)} disabled={busy} autoComplete="off" />{connectionError && <p className="connection-error" role="status">{connectionError}</p>}<p>ต้องเปิดเครื่องและตัวเปิด DataView ไว้ระหว่างใช้งาน หาก Chrome ขอให้เข้าสู่ระบบหรือยืนยันตัวตน ให้ทำที่เครื่องดึงข้อมูล</p></div>
          </details>
          <form onSubmit={submit}>
            <fieldset disabled={busy} className="form-fieldset">
              <legend className="sr-only">ตั้งค่าการวิเคราะห์</legend>
              <div className="platform-options" role="group" aria-label="แพลตฟอร์ม">{platforms.map(p => <button className={`platform-option ${platform === p ? "selected" : ""}`} key={p} type="button" onClick={() => { setPlatform(p); setUrl(""); setError(""); }} aria-pressed={platform === p}><PlatformMark platform={p} /><span><strong>{p === "Facebook" ? "Facebook Reels" : p}</strong><small>{p === "YouTube" ? "วิดีโอ · Shorts · ไลฟ์" : p === "TikTok" ? "วิดีโอจากโปรไฟล์" : "Reels จากเพจหรือโปรไฟล์"}</small></span><span className="radio-indicator">{platform === p && <span />}</span></button>)}</div>
              <div className="input-section"><label htmlFor="profile-url">ลิงก์ช่องหรือโปรไฟล์ <span className="required">*</span></label><div className="url-wrap"><Icon name="link" size={19} /><input id="profile-url" name="url" type="url" required maxLength={2048} value={url} onChange={e => setUrl(e.target.value)} placeholder={examples[platform]} autoComplete="off" spellCheck={false} /></div><p className="input-help">ใช้ลิงก์{platform === "YouTube" ? "หน้าช่อง YouTube" : platform === "TikTok" ? "โปรไฟล์ TikTok" : "เพจหรือโปรไฟล์ Facebook"} ที่เปิดเป็นสาธารณะ</p></div>
              <div className="options-row"><div className="scope-field"><label htmlFor="scope">เลือกคลิปที่ต้องการวิเคราะห์</label><select id="scope" value={mode} onChange={e => setMode(e.target.value as Mode)}><option value="latest">คลิปล่าสุด</option><option value="days">ย้อนหลังตามวัน</option><option value="all">ทั้งหมดของช่อง</option></select></div>{mode !== "all" && <div className="amount-field"><label htmlFor="amount">{mode === "latest" ? "จำนวนคลิป" : "จำนวนวันย้อนหลัง"}</label><div className="amount-wrap"><input id="amount" type="number" min="1" step="1" required value={mode === "latest" ? clips : days} onChange={e => mode === "latest" ? setClips(e.target.value) : setDays(e.target.value)} /><span>{mode === "latest" ? "คลิป" : "วัน"}</span></div></div>}</div>
              {platform === "YouTube" && <div className="youtube-options"><span>ประเภทวิดีโอ</span>{(Object.keys(youtubeTabs) as YoutubeTab[]).map(tab => <label key={tab}><input type="checkbox" checked={tabs.includes(tab)} onChange={e => setTabs(prev => e.target.checked ? [...prev, tab] : prev.filter(t => t !== tab))} />{youtubeTabs[tab]}</label>)}</div>}
              <div className="form-bottom"><span><Icon name="info" size={17} />ยอดวิวสะสม ณ เวลาที่อ่านข้อมูล</span><button className="primary-button" type="submit"><Icon name="chart" size={19} />เริ่มวิเคราะห์</button></div>
            </fieldset>
          </form>
          {busy && <div className="progress-box" role="status"><div className="progress-text"><span className="spinner" /><div><strong>{status}</strong><span>การอ่านข้อมูลอาจใช้เวลาหลายนาที · {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span></div></div><button className="cancel-button" type="button" onClick={() => abortRef.current?.abort()}><Icon name="stop" size={15} />ยกเลิก</button></div>}
          {!busy && status && <p className="status-message" role="status"><Icon name="check" size={16} />{status}</p>}
          {error && <div className="error-box" role="alert"><Icon name="info" /><span>{error}</span></div>}
        </section>

        <section className="results" ref={resultRef} aria-labelledby="results-title" aria-busy={busy}>
          <div className="results-heading"><div><h2 id="results-title">ผลการวิเคราะห์</h2><p>{result ? `${result.platform} · ${scopeText(result)}` : "ข้อมูลสำคัญของช่อง สรุปไว้ในที่เดียว"}</p></div>{result && <span className={`result-badge ${result.complete ? "complete" : "partial"}`}><Icon name={result.complete ? "check" : "info"} size={15} />{result.complete ? "อ่านข้อมูลครบตามเงื่อนไข" : "ข้อมูลบางส่วน"}</span>}</div>
          {result && <div className="result-source"><a href={result.url} target="_blank" rel="noopener noreferrer">{result.url}</a><span>อ่านเมื่อ {dateText(result.collectedAt)} {new Intl.DateTimeFormat("th-TH", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bangkok" }).format(new Date(result.collectedAt))} น.</span></div>}
          <div className="metric-grid">{([
            { icon: "play", label: "จำนวนคลิป", value: result?.videos.length, unit: "คลิป", help: result ? "คลิปที่เลือกได้ตามเงื่อนไข" : "คลิปที่อยู่ในช่วงที่เลือก" },
            { icon: "eye", label: "ยอดวิวรวม", value: result?.totalViews, unit: "วิว", help: result ? `จาก ${number(result.knownViews)} คลิปที่อ่านยอดวิวได้` : "รวมยอดวิวจากคลิปที่อ่านได้" },
            { icon: "average", label: "ยอดวิวเฉลี่ย", value: result?.averageViews, unit: "วิว / คลิป", help: "เฉลี่ยเฉพาะคลิปที่มีข้อมูลยอดวิว" },
          ] as const).map((card, i) => <div key={card.label} className={`metric-card metric-${i}`}><div className="metric-top"><span>{card.label}</span><span className="metric-icon"><Icon name={card.icon} size={21} /></span></div><div className="metric-value">{number(card.value, i === 2 && result ? 2 : 0)}<span>{card.unit}</span></div><p>{card.help}</p></div>)}</div>
          {result && (!result.complete || result.notes.length > 0 || result.missingDates > 0 || result.knownViews < result.videos.length) && <div className="notice" role="status"><Icon name="info" /><div><strong>อ่านข้อมูลได้บางส่วน</strong>{result.notes.map((note, i) => <p key={i}>{note}</p>)}{result.missingDates > 0 && <p>ตรวจวันโพสต์ไม่ได้ {number(result.missingDates)} คลิป จึงไม่นำมาคัดเลือกในโหมดนี้</p>}{result.knownViews < result.videos.length && <p>อ่านยอดวิวไม่ได้ {number(result.videos.length - result.knownViews)} คลิป จึงไม่นำมาคำนวณค่าเฉลี่ย</p>}{!result.notes.length && <p>ผลลัพธ์นี้ครอบคลุมเฉพาะข้อมูลที่ตรวจสอบได้ในรอบนี้</p>}</div></div>}
          <div className="table-panel"><div className="table-heading"><div><Icon name="play" /><h3>รายการคลิป</h3>{result && <span className="count-badge">{number(result.videos.length)}</span>}</div><span>เรียงตามวันที่โพสต์ล่าสุด</span></div>{!result ? <div className="empty-state"><div className="empty-art" aria-hidden="true"><div className="mini-card"><span /><span /><span /></div><span className="empty-glass"><Icon name="chart" size={27} /></span></div><h3>{busy ? "กำลังอ่านข้อมูลจากช่องของคุณ" : "พร้อมสำรวจข้อมูลช่องของคุณ"}</h3><p>{busy ? "ผลการวิเคราะห์จะแสดงที่นี่เมื่ออ่านข้อมูลเสร็จ" : "วางลิงก์ด้านบน แล้วกดเริ่มวิเคราะห์เพื่อดูยอดวิวและรายการคลิป"}</p><div className="empty-platforms">{platforms.map(p => <PlatformMark key={p} platform={p} small />)}</div></div> : result.videos.length === 0 ? <div className="empty-state"><Icon name="play" size={35} /><h3>ไม่พบคลิปตามเงื่อนไขที่เลือก</h3><p>ลองเปลี่ยนช่วงวัน จำนวนคลิป หรือประเภทวิดีโอแล้ววิเคราะห์อีกครั้ง</p></div> : <div className="table-scroll"><table><thead><tr><th scope="col">คลิป</th><th scope="col">วันที่เผยแพร่</th><th scope="col" className="views-column">ยอดวิว</th><th scope="col"><span className="sr-only">ลิงก์คลิป</span></th></tr></thead><tbody>{result.videos.map((video, i) => <tr key={video.url}><td><div className="video-cell"><PlatformMark platform={result.platform} small /><span>คลิปที่ {number(i + 1)}<small>{video.url.split(/[/?]/).filter(Boolean).at(-1)}</small></span></div></td><td>{video.day ? dateText(`${video.day}T00:00:00+07:00`) : <span className="muted">ไม่ทราบวันที่</span>}</td><td className="views-column">{video.views === null ? <span className="muted">อ่านไม่ได้</span> : number(video.views)}</td><td><a className="clip-link" href={video.url} target="_blank" rel="noopener noreferrer" aria-label={`เปิดคลิปที่ ${i + 1}`}>เปิดคลิป</a></td></tr>)}</tbody></table></div>}</div>
          <div className="data-note"><Icon name="info" size={16} /><span>ยอดวิวเป็นยอดสะสมของคลิป ณ เวลาที่อ่าน ไม่ใช่ยอดวิวที่เพิ่มขึ้นเฉพาะช่วงวัน{result?.platform === "Facebook" ? " · Facebook อาจแสดงยอดวิวแบบปัดเศษ" : ""}</span></div>
        </section>
        <footer><span>DataView <span className="footer-divider">/</span> Social analytics, made clear.</span><span>by <strong>Cheese Ponrakit</strong></span></footer>
      </main>
    </div>
  </div>;
}
