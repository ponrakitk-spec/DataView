import os
import sys

# ตรวจสอบและติดตั้ง yt-dlp อัตโนมัติหากยังไม่มี
try:
    import yt_dlp
except ImportError:
    print("ไม่พบไลบรารี yt-dlp ในระบบ กำลังติดตั้งให้โดยอัตโนมัติ...")
    os.system(f'"{sys.executable}" -m pip install yt-dlp')
    import yt_dlp

def download_youtube_video():
    print("="*50)
    print("โปรแกรมดาวน์โหลดวิดีโอ YouTube (Full HD 1080p)")
    print("="*50)
    
    url = input("กรุณาวางลิงก์ YouTube ที่ต้องการดาวน์โหลด: ")
    
    if not url.strip():
        print("คุณไม่ได้ป้อนลิงก์วิดีโอ กรุณาลองใหม่อีกครั้ง")
        return
        
    print("\nกำลังเตรียมการดาวน์โหลด โปรดรอสักครู่...")
    
    # ตั้งค่าตัวเลือกของ yt-dlp เพื่อดึง 1080p เป็นหลัก
    ydl_opts_base = {
        # พยายามดึงวิดีโอสูงสุดที่ไม่เกิน 1080p แบบ mp4 + เสียงแบบ m4a และรวมเป็น mp4
        # ถ้าไม่มีจะใช้แบบที่มีรวมกันมาให้เลยแทน
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
        'merge_output_format': 'mp4',
        'outtmpl': '%(title)s.%(ext)s',
    }
    
    # วนลูปพยายามใช้คุกกี้จากเบราว์เซอร์ที่ไม่ได้ถูกเปิดค้างไว้
    browsers_to_try = ['edge', 'chrome', 'firefox', 'brave', 'opera']
    success = False
    
    for browser in browsers_to_try:
        print(f"\n[ระบบ] กำลังพยายามใช้คุกกี้จาก {browser.title()} เพื่อเชื่อมต่อ...")
        ydl_opts = ydl_opts_base.copy()
        ydl_opts['cookiesfrombrowser'] = (browser,)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            success = True
            break # ถ้าสำเร็จให้ออกจากลูปเลย
        except Exception as e:
            error_msg = str(e)
            if "Could not copy" in error_msg or "Could not find" in error_msg or "not supported" in error_msg:
                print(f"[ระบบ] ข้าม {browser.title()} (เบราว์เซอร์อาจเปิดอยู่ หรือไม่มีในเครื่อง)")
            else:
                print(f"[ระบบ] ข้าม {browser.title()} (เกิดข้อผิดพลาด: {error_msg})")
                
    if success:
        print("\n✅ ดาวน์โหลดวิดีโอเสร็จสมบูรณ์!")
        print("ไฟล์วิดีโอถูกบันทึกไว้ในโฟลเดอร์เดียวกับโปรแกรมนี้")
    else:
        print(f"\n❌ เกิดข้อผิดพลาดระหว่างดาวน์โหลด: ไม่สามารถดึงคุกกี้ได้เลย")
        print("\n[ คำแนะนำสำหรับแก้ปัญหา ]")
        print("1. โปรแกรมไม่สามารถดึงข้อมูลคุกกี้ได้เพราะ 'เบราว์เซอร์กำลังเปิดใช้งานอยู่'")
        print("2. กรุณาปิดเบราว์เซอร์ทั้งหมด (ทั้ง Chrome, Edge ฯลฯ) ให้หมดทุกหน้าต่าง")
        print("3. กลับมาที่ VS Code แล้วรันโปรแกรมใหม่อีกครั้ง")
        print("4. หากภาพและเสียงไม่รวมกัน โปรดเปิด PowerShell แล้วพิมพ์: winget install -e --id Gyan.FFmpeg")

if __name__ == '__main__':
    download_youtube_video()
    
    # ให้หน้าต่างไม่ปิดทันทีเพื่อให้ผู้ใช้อ่านข้อความ
    print("\n" + "="*50)
    input("กด Enter เพื่อปิดโปรแกรม...")
