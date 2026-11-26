# DataView

**DataView by Cheese Ponrakit**

## Web app — Next.js + TypeScript

เว็บไซต์: https://dataview-one.vercel.app

เว็บรองรับ YouTube, TikTok และ Facebook Reels เหมือนโปรแกรมเดิม: เลือกย้อนหลังตามวัน คลิปล่าสุด หรือทั้งหมดของช่อง รวมถึงวิดีโอปกติ / Shorts / ไลฟ์ย้อนหลังของ YouTube แสดงจำนวนคลิป ยอดวิวรวม ยอดวิวเฉลี่ย และลิงก์เปิดคลิป

ตามรูปแบบที่เลือก เว็บอยู่บน Vercel และส่งงานมาดึงข้อมูลด้วย Python/Chrome บนเครื่องของคุณ งานอ่านทั้งช่องทำงานต่อได้โดยไม่ผูกกับระยะเวลาของคำขอ Vercel

### เปิดใช้งาน

เครื่องต้องมี Python, Google Chrome และแพ็กเกจใน `requirements.txt` จากโฟลเดอร์โปรเจกต์รัน:

```powershell
python -m pip install -r requirements.txt
python worker/start.py
```

หรือเรียก `Start-DataView.ps1` ตัวเปิดจะดาวน์โหลด `cloudflared` จาก release ทางการของ Cloudflare ในครั้งแรก เปิดช่องทาง HTTPS และเปิดเว็บพร้อมเชื่อมต่อเครื่องอัตโนมัติ ต้องเปิดเครื่องและตัวเปิดนี้ไว้ตลอดการใช้งาน หากแพลตฟอร์มขอให้ล็อกอินหรือยืนยันตัวตน ให้ดำเนินการในหน้าต่าง Chrome ของ DataView บนเครื่อง

ใช้ Chrome profile แยกใน `.dataview/chrome-profile` เพื่อเก็บการล็อกอินของ DataView แยกจาก Chrome ส่วนตัว ข้อมูลเชื่อมต่อและรหัสเข้าถึงอยู่ใน `.dataview/connection.json` ซึ่งถูก Git ignore แล้ว เว็บเก็บรหัสใน session ของแท็บนั้น และนำรหัสออกจาก address bar หลังเปิดหน้าเว็บ อย่าแชร์ลิงก์ที่มีรหัสเชื่อมต่อหรือไฟล์นี้

หยุดด้วย Ctrl+C ในหน้าต่างตัวเปิด หรือรัน:

```powershell
python worker/start.py --stop
```

เมื่อเปิดใหม่ ลิงก์เครื่องดึงข้อมูลจะเปลี่ยน ให้ใช้หน้าเว็บที่ตัวเปิดเปิดให้ใหม่ ไม่ต้อง deploy เว็บซ้ำ [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) เป็นช่องทางชั่วคราว ไม่มีการรับประกัน uptime

### พัฒนาและตรวจสอบ

โค้ดเว็บอยู่ใน `web/` ใช้ Node.js 24:

```powershell
cd web
npm ci
npm run dev
npm test
npm run typecheck
npm run build
```

ทดสอบ backend จากโฟลเดอร์โปรเจกต์: `python -m unittest discover -s worker -p test_server.py -v`

ทดสอบข้อมูลจริงหลังเปิด worker: `node web/scripts/smoke-live.mjs https://dataview-one.vercel.app` (จะเปิด Chrome จริง)

ดูรายละเอียดสถาปัตยกรรมและข้อจำกัดใน [web/README.md](web/README.md)

## โปรแกรม Windows เดิม

โปรแกรม Windows สำหรับวิเคราะห์ยอดวิวคลิปของ YouTube, TikTok และ Facebook Reels

## ใช้งาน

เปิด `dist/DataView.exe` บน Windows ที่มี Google Chrome และอินเทอร์เน็ต เลือกแพลตฟอร์ม ใส่ลิงก์ช่องหรือโปรไฟล์ แล้วเลือกช่วงย้อนหลังตามวัน จำนวนคลิปล่าสุด หรือทั้งหมดของช่อง สำหรับ YouTube เลือกวิดีโอปกติ Shorts และไลฟ์ย้อนหลังได้

แดชบอร์ดแสดงจำนวนคลิป ยอดวิวรวม ยอดวิวเฉลี่ย และคลิปรายการที่อ่านได้ หากเว็บไซต์ส่งข้อมูลไม่ครบ โปรแกรมจะแจ้งว่าผลลัพธ์เป็นข้อมูลบางส่วน

## เรียกจาก Python

ติดตั้งแพ็กเกจใน `requirements.txt` แล้วเรียก `python dataview_app.py` ต้องมี Google Chrome ติดตั้งอยู่
