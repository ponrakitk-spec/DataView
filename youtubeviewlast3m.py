from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
from datetime import datetime, timedelta
import re

def parse_view_count(text):
    """
    แปลงข้อความยอดวิวเป็นตัวเลข (รองรับทั้ง K, M, B และภาษาไทย)
    ตัวอย่าง: '1.2M views', '5.5K การดู', '1,000 views'
    """
    if not text:
        return 0
    
    # ลบคำว่า views, การดู และช่องว่าง
    clean_text = text.lower().replace('views', '').replace('view', '').replace('การดู', '').replace('ครั้ง', '').strip()
    
    multiplier = 1
    if 'k' in clean_text:
        multiplier = 1000
        clean_text = clean_text.replace('k', '')
    elif 'm' in clean_text or 'ล้าน' in clean_text:
        multiplier = 1000000
        clean_text = clean_text.replace('m', '').replace('ล้าน', '')
    elif 'b' in clean_text or 'พันล้าน' in clean_text:
        multiplier = 1000000000
        clean_text = clean_text.replace('b', '').replace('พันล้าน', '')
        
    try:
        # ลบ comma ออกก่อนแปลงเป็น float
        number_val = float(clean_text.replace(',', ''))
        return int(number_val * multiplier)
    except ValueError:
        return 0

def parse_date(date_text):
    """
    แปลงข้อความวันที่เป็น datetime object
    รองรับรูปแบบ: 'X days ago', 'X months ago', 'X weeks ago', 'X hours ago'
    และรูปแบบภาษาไทย: 'X วันที่แล้ว', 'X เ ดือนที่แล้ว', 'X สัปดาห์ที่แล้ว'
    """
    if not date_text:
        return None
    
    date_text = date_text.lower().strip()
    
    try:
        # Regular expression สำหรับ pattern: "3 days ago"
        match = re.search(r'(\d+)\s+(day|week|month|hour|minute)', date_text)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            
            now = datetime.now()
            if unit == 'day':
                return now - timedelta(days=num)
            elif unit == 'week':
                return now - timedelta(weeks=num)
            elif unit == 'month':
                return now - timedelta(days=num * 30)
            elif unit == 'hour':
                return now - timedelta(hours=num)
            elif unit == 'minute':
                return now - timedelta(minutes=num)
        
        # ลองแปลง pattern ภาษาไทย
        match = re.search(r'(\d+)\s+(วัน|สัปดาห์|เดือน|ชั่วโมง|นาที)', date_text)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            
            now = datetime.now()
            if unit == 'วัน':
                return now - timedelta(days=num)
            elif unit == 'สัปดาห์':
                return now - timedelta(weeks=num)
            elif unit == 'เดือน':
                return now - timedelta(days=num * 30)
            elif unit == 'ชั่วโมง':
                return now - timedelta(hours=num)
            elif unit == 'นาที':
                return now - timedelta(minutes=num)
        
        return None
    except:
        return None

def is_within_3_months(date_obj):
    """
    ตรวจสอบว่าวิดีโออยู่ในช่วง 3 เดือนที่แล้วหรือไม่
    """
    if not date_obj:
        return False
    
    now = datetime.now()
    three_months_ago = now - timedelta(days=90)
    
    return date_obj >= three_months_ago

def main():
    # รับ URL จากผู้ใช้
    target_url = input("Please enter YouTube Channel URL (e.g., https://www.youtube.com/@ChannelName/videos): ")
    
    if not target_url:
        print("URL cannot be empty.")
        return

    # ตั้งค่า Chrome Driver
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # สามารถเปิด headless ได้ถ้าต้องการ
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        print(f"Opening {target_url}...")
        driver.get(target_url)
        
        # รอให้เว็บโหลด
        time.sleep(3)
        
        print("Scrolling to load videos... (Getting last 3 months)")
        
        scroll_pause_time = 2.5
        last_height = driver.execute_script("return document.documentElement.scrollHeight")
        three_months_ago = datetime.now() - timedelta(days=90)
        
        scroll_count = 0
        reached_older_videos = False
        
        while not reached_older_videos:
            # เลื่อนลงไปล่างสุด
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            
            # รอโหลด
            time.sleep(scroll_pause_time)
            
            # ตรวจสอบวิดีโอที่เก่าที่สุด
            video_cn = 'ytd-rich-item-renderer'
            containers = driver.find_elements(By.TAG_NAME, video_cn)
            if not containers:
                containers = driver.find_elements(By.TAG_NAME, 'ytd-grid-video-renderer')
            
            # ตรวจสอบวิดีโอล่าสุด
            if containers:
                last_item = containers[-1]
                try:
                    meta_spans = last_item.find_elements(By.CSS_SELECTOR, '#metadata-line span')
                    date_text = ""
                    for sp in meta_spans:
                        t = sp.text.strip()
                        if t and 'ago' in t.lower():
                            date_text = t
                            break
                    
                    if date_text:
                        last_date = parse_date(date_text)
                        if last_date and last_date < three_months_ago:
                            print(f"Found video older than 3 months: {date_text}")
                            reached_older_videos = True
                except:
                    pass
            
            # ตรวจสอบความสูงใหม่
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            
            scroll_count += 1
            print(f"Scrolled {scroll_count} times... Videos loaded: {len(containers)}")

            if new_height == last_height:
                # ลองรอเพิ่มอีกนิดเผื่อเน็ตช้า
                time.sleep(2)
                new_height = driver.execute_script("return document.documentElement.scrollHeight")
                if new_height == last_height:
                    print("Reached end of page.")
                    break
            
            last_height = new_height
            
        print("Analyzing videos from last 3 months...")
        
        # Selectors สำหรับ container ของวิดีโอ
        video_cn = 'ytd-rich-item-renderer'
        containers = driver.find_elements(By.TAG_NAME, video_cn)
        
        # กรณีเป็น layout แบบเก่าหรือ grid
        if not containers:
             containers = driver.find_elements(By.TAG_NAME, 'ytd-grid-video-renderer')
        
        print(f"Found {len(containers)} total videos.")

        all_view_counts = []
        
        for idx, item in enumerate(containers, 1):
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
                    elif "ago" in t.lower():
                        date_text = t
                
                # Fallback ถ้าไม่เจอใน metadata-line
                if not view_text:
                    inline_metas = item.find_elements(By.CLASS_NAME, 'inline-metadata-item')
                    for sp in inline_metas:
                        t = sp.text.strip()
                        if "views" in t.lower() or "การดู" in t:
                            view_text = t
                            break

                # ตรวจสอบวิดีโอนี้อยู่ในช่วง 3 เดือนไหม
                if date_text:
                    date_obj = parse_date(date_text)
                    if date_obj and is_within_3_months(date_obj):
                        if view_text:
                            v_val = parse_view_count(view_text)
                            if v_val >= 0:
                                all_view_counts.append(v_val)
                                print(f"Video {idx}: {view_text} | {date_text} ({v_val:,} views)")
                
            except Exception as e:
                pass

        if all_view_counts:
            avg_views = sum(all_view_counts) / len(all_view_counts)
            print("=" * 50)
            print(f"Summary (Last 3 Months)")
            print(f"Total Videos Processed: {len(all_view_counts)}")
            print(f"Average Views: {avg_views:,.2f}")
            print(f"Min Views: {min(all_view_counts):,}")
            print(f"Max Views: {max(all_view_counts):,}")
            print("=" * 50)
        else:
            print("No video view counts found in the last 3 months.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    main()
