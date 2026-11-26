from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
from dataview_analysis import labeled_views

def parse_view_count(text):
    """
    แปลงข้อความยอดวิวเป็นตัวเลข (รองรับทั้ง K, M, B และภาษาไทย)
    ตัวอย่าง: '1.2M views', '5.5K การดู', '1,000 views'
    """
    if not text:
        return None
    value = labeled_views(text)
    return value if value is not None else labeled_views(f"{text} views")

def get_days_ago(text):
    """
    แปลงข้อความวันที่แบบ Relative เป็นจำนวนวันที่ผ่านมา
    คืนค่าเป็น int (จำนวนวัน) หรือ None ถ้าแปลค่าไม่ได้
    """
    text = text.lower()
    # Regex หาตัวเลขและหน่วยเวลา
    # รองรับ: sec, min, hour, day, week, month, year (และภาษาไทย)
    match = re.search(r'(\d+)\s*(sec|min|hour|day|week|month|year|วิ|นาที|ชม|ชั่วโมง|วัน|อาทิตย์|สัปดาห์|เดือน|ปี)', text)
    
    if match:
        qty = int(match.group(1))
        unit = match.group(2)
        
        if unit in ['sec', 'วิ', 'min', 'นาที', 'hour', 'ชม', 'ชั่วโมง']:
            return 0 # ภายใน 1 วัน
        elif unit in ['day', 'วัน']:
            return qty
        elif unit in ['week', 'อาทิตย์', 'สัปดาห์']:
            return qty * 7
        elif unit in ['month', 'เดือน']:
            return qty * 30 # โดยประมาณ
        elif unit in ['year', 'ปี']:
            return qty * 365
            
    return None

def main():
    # รับ URL จากผู้ใช้
    target_url = input("Please enter YouTube Video URL (e.g., https://www.youtube.com/@ChannelName/videos): ")
    
    if not target_url:
        print("URL cannot be empty.")
        return

    # ตั้งค่า Chrome Driver
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        print(f"Opening {target_url}...")
        driver.get(target_url)
        
        # รอให้เว็บโหลด
        time.sleep(3)
        
        print("Scrolling... (Checking dates to stop early)")
        
        scroll_pause_time = 2
        last_height = driver.execute_script("return document.documentElement.scrollHeight")
        
        max_scrolls = 50 
        scroll_count = 0
        
        video_cn = 'ytd-rich-item-renderer'
        
        while scroll_count < max_scrolls:
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            time.sleep(scroll_pause_time)
            
            # ตรวจสอบวันที่ของคลิปล่าสุดที่โหลดมาเพื่อดูว่าเกิน 30 วันหรือยัง
            # ดึงเฉพาะตัวท้ายๆ มาเช็คก็พอ
            try:
                # Find recent containers
                containers = driver.find_elements(By.TAG_NAME, video_cn)
                if not containers:
                    containers = driver.find_elements(By.TAG_NAME, 'ytd-grid-video-renderer')
                
                # Check the last few items
                check_last_n = 5
                reached_limit = False
                
                if containers:
                    for item in containers[-check_last_n:]:
                        # หา text วันที่
                        text_content = item.text.lower()
                        # ถ้าเจอ 'month' หรือ 'year' หรือ 'เดือน' หรือ 'ปี' แสดงว่าอาจจะเกิน 30 วันแล้ว
                        # แต่ต้องระวัง '1 month ago' อาจจะคาบเกี่ยว แต่ถ้าเจอ '2 months' 'year' คือจบเลย
                        
                        # เพื่อความชัวร์ ใช้ get_days_ago
                        # ต้องหา element วันที่ให้ได้แม่นๆ หรือจะ parse จาก text รวมก็ได้ถ้าง่าย
                        # ลอง regex หา x month/year ago ใน text รวมของ element
                        
                        date_match = re.search(r'(\d+)\s*(month|year|เดือน|ปี)', text_content)
                        if date_match:
                            days = get_days_ago(date_match.group(0))
                            if days and days > 35: # เผื่อ buffer นิดหน่อย
                                reached_limit = True
                                break
                    
                if reached_limit:
                    print("Found videos older than 30 days. Stopping scroll.")
                    break
                    
            except Exception:
                pass # อย่าเพิ่ง error ถ้าหาไม่เจอ

            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            if new_height == last_height:
                print("Reached end of page.")
                break
            last_height = new_height
            scroll_count += 1
            print(f"Scrolled {scroll_count} times...")
            
        print("Analyzing loaded videos...")
        
        containers = driver.find_elements(By.TAG_NAME, video_cn)
        if not containers:
             containers = driver.find_elements(By.TAG_NAME, 'ytd-grid-video-renderer')

        print(f"Found {len(containers)} total containers. Filtering for last 30 days...")

        valid_view_counts = []
        
        for item in containers:
            try:
                # พยายามหา metadata line
                meta_spans = item.find_elements(By.CSS_SELECTOR, '#metadata-line span')
                
                view_text = ""
                date_text = ""
                
                for sp in meta_spans:
                    t = sp.text.strip()
                    if not t: continue
                    
                    if "views" in t.lower() or "การดู" in t:
                        view_text = t
                    elif any(x in t for x in ['ago', 'ผ่านมา', 'ที่แล้ว']):
                        date_text = t
                
                if not view_text or not date_text:
                    inline_metas = item.find_elements(By.CLASS_NAME, 'inline-metadata-item')
                    for sp in inline_metas:
                        t = sp.text.strip()
                        if "views" in t.lower() or "การดู" in t:
                            view_text = t
                        elif any(x in t for x in ['ago', 'ผ่านมา', 'ที่แล้ว']):
                            date_text = t

                if view_text and date_text:
                    days = get_days_ago(date_text)
                    
                    if days is not None:
                        if days <= 30:
                            v_val = parse_view_count(view_text)
                            if v_val is not None:
                                valid_view_counts.append(v_val)
                                # แสดงวันที่ด้วย
                                print(f" [PASS] {view_text} | Posted: {date_text}")
                        else:
                            # print(f" [SKIP] {view_text} | {date_text} ({days} days ago)")
                            pass
                
            except Exception as e:
                pass

        if valid_view_counts:
            avg_views = sum(valid_view_counts) / len(valid_view_counts)
            print("-" * 40)
            print(f"Summary (Last 30 Days Only)")
            print(f"Total Videos: {len(valid_view_counts)}")
            print(f"Average Views: {avg_views:,.2f}")
            print("-" * 40)
        else:
            print("No videos found within the last 30 days.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    main()
