# DataView by Cheese Ponrakit

Next.js App Router + TypeScript + React. Production: https://dataview-one.vercel.app

## การทำงาน

1. ตัวเปิด `../worker/start.py` เปิด Python worker ที่ `127.0.0.1:8765` และ Cloudflare Quick Tunnel ผ่าน HTTPS
2. ตัวเปิดเปิดเว็บด้วยลิงก์ส่วนตัว เว็บนำข้อมูลการเชื่อมต่อมาเก็บใน session ของแท็บ แล้วล้าง fragment ออกจาก address bar
3. Next.js API ตรวจลิงก์และส่งคำขอที่มีรหัสเข้าถึงไปยัง worker รองรับเฉพาะ HTTPS Quick Tunnel root และไม่ตาม redirect
4. Worker รับงาน เรียก `dataview_analysis.analyze` เดิม และเปิด Chrome ของ DataView ทีละงาน เว็บอ่านสถานะทุกประมาณ 1.2 วินาที
5. เมื่อเสร็จ เว็บแสดงข้อมูลจริงเท่านั้น หากแพลตฟอร์มส่งข้อมูลไม่ครบหรือขอให้ล็อกอิน จะแสดงคำเตือน/ข้อผิดพลาด

รหัสเชื่อมต่อไม่ได้อยู่ใน source หรือ Vercel environment ผู้ใช้ต้องเปิดเว็บจากตัวเปิดหรือกรอกข้อมูลในส่วนตั้งค่าการเชื่อมต่อ รหัสเดียวกันใช้ยืนยันตัวตนที่ worker ทุก endpoint รวมถึง health check

## ฟังก์ชัน

- YouTube: วิดีโอปกติ, Shorts, ไลฟ์ย้อนหลังที่จบแล้ว
- TikTok: คลิปวิดีโอจากโปรไฟล์ เลือกคลิปล่าสุดตามวันที่จริง รวมคลิปปักหมุดเมื่อวันที่เข้าเงื่อนไข
- Facebook: Reels ของเพจหรือโปรไฟล์ที่เข้าถึงได้
- เลือกย้อนหลังตามวัน (เวลาไทย รวมวันนี้), N คลิปล่าสุด, หรือทั้งช่อง
- จำนวนคลิป ยอดวิวรวม ค่าเฉลี่ยเฉพาะคลิปที่อ่านยอดวิวได้ วันที่โพสต์ ลิงก์เปิดคลิป สถานะความครบถ้วน และยกเลิกงาน

## รันในเครื่อง

ใช้ Node.js 24, `npm ci` และ `npm run dev` เปิด worker จากโฟลเดอร์โปรเจกต์ด้วย `python worker/start.py` จากนั้นกรอกข้อมูลเชื่อมต่อจาก `.dataview/connection.json` ในหน้าเว็บ local

## ตรวจสอบ

`npm test`, `npm run typecheck`, `npm run build`

เมื่อ worker ออนไลน์: `node scripts/check-ui.mjs http://127.0.0.1:3001` (ต้องมีเว็บรันที่พอร์ตนี้) และ `node scripts/smoke-live.mjs https://dataview-one.vercel.app`

UI checks ใช้ Chrome แบบ headless ผ่าน Playwright; ไม่ใช่การตรวจด้วย Windows Computer Use ชุดทดสอบ worker แยก fixture ออกจากการทดสอบข้อมูลจริง

## ข้อจำกัด

- ต้องเปิดเครื่อง worker และมีอินเทอร์เน็ต เว็บไซต์ Vercel ยังเปิดดูได้เมื่อเครื่องปิด แต่เริ่มวิเคราะห์ไม่ได้
- เมื่อแพลตฟอร์มร้องขอ ผู้ใช้ต้องล็อกอิน/ยืนยันตัวตนใน Chrome บนเครื่อง worker การรันบนเครื่องไม่ได้รับประกันว่าทุกโปรไฟล์จะอ่านได้
- ยอดวิวคือยอดสะสมตอนอ่าน ไม่ใช่จำนวนวิวที่เพิ่มขึ้นในช่วงวัน Facebook อาจส่งยอดแบบปัดเศษ
- หน้าต่าง Chrome ใช้ profile ของ DataView แยกจาก Chrome ส่วนตัว
- งานอยู่ในหน่วยความจำของ worker: หายเมื่อหยุด/รีสตาร์ต ผลที่เสร็จเก็บหนึ่งชั่วโมง ถ้าไม่มีการอ่านสถานะงาน 10 นาที งานจะถูกยกเลิก
- Quick Tunnel มี hostname ใหม่เมื่อเปิดใหม่ และไม่มี uptime guarantee ให้เปิดเว็บจากตัวเปิดอีกครั้งหลัง restart
- Deploy ด้วย CLI จาก `web/`: `vercel --prod --scope ponrakit` การเชื่อม GitHub อัตโนมัติยังไม่สำเร็จ
