from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
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
        
        print("Loading videos... (Getting last 10 clips)")
        
        scroll_pause_time = 2.5
        last_height = driver.execute_script("return document.documentElement.scrollHeight")
        
        scroll_count = 0
        target_videos = 10
        
        while True:
            # ตรวจสอบจำนวนวิดีโอที่โหลดได้แล้ว
            video_cn = 'ytd-rich-item-renderer'
            containers = driver.find_elements(By.TAG_NAME, video_cn)
            
            if not containers:
                containers = driver.find_elements(By.TAG_NAME, 'ytd-grid-video-renderer')
            
            # ถ้าจำนวนวิดีโอครบ 10 แล้วให้หยุด
            if len(containers) >= target_videos:
                print(f"Found {len(containers)} videos (using last {target_videos})")
                break
            
            # เลื่อนลงไปล่างสุด
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            
            # รอโหลด
            time.sleep(scroll_pause_time)
            
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
            
        print("Analyzing last 10 videos...")
        
        # Selectors สำหรับ container ของวิดีโอ
        video_cn = 'ytd-rich-item-renderer'
        containers = driver.find_elements(By.TAG_NAME, video_cn)
        
        # กรณีเป็น layout แบบเก่าหรือ grid
        if not containers:
             containers = driver.find_elements(By.TAG_NAME, 'ytd-grid-video-renderer')
        
        # เอาเฉพาะ 10 อันแรก (ล่าสุด)
        containers = containers[:target_videos]
        
        print(f"Found {len(containers)} videos to analyze.")

        all_view_counts = []
        
        for idx, item in enumerate(containers, 1):
            try:
                # พยายามหา metadata line
                # Selector นี้มักจะครอบคลุม both views and date
                meta_spans = item.find_elements(By.CSS_SELECTOR, '#metadata-line span')
                
                view_text = ""
                
                for sp in meta_spans:
                    t = sp.text.strip()
                    if not t: continue
                    
                    if "views" in t.lower() or "การดู" in t:
                        view_text = t
                        break # เจอ views แล้วจบเลยสำหรับ item นี้
                
                # Fallback ถ้าไม่เจอใน metadata-line
                if not view_text:
                    inline_metas = item.find_elements(By.CLASS_NAME, 'inline-metadata-item')
                    for sp in inline_metas:
                        t = sp.text.strip()
                        if "views" in t.lower() or "การดู" in t:
                            view_text = t
                            break

                if view_text:
                    v_val = parse_view_count(view_text)
                    if v_val >= 0: # รวม 0 วิวด้วยก็ได้ หรือจะเอา > 0 ก็แล้วแต่ (ปกติคลิปมีวิว)
                        all_view_counts.append(v_val)
                        print(f"Clip {idx}: {view_text} ({v_val:,} views)")
                
            except Exception as e:
                pass

        if all_view_counts:
            avg_views = sum(all_view_counts) / len(all_view_counts)
            print("=" * 50)
            print(f"Summary (Last {target_videos} Videos)")
            print(f"Total Videos Processed: {len(all_view_counts)}")
            print(f"Average Views: {avg_views:,.2f}")
            print(f"Min Views: {min(all_view_counts):,}")
            print(f"Max Views: {max(all_view_counts):,}")
            print("=" * 50)
        else:
            print("No video view counts found.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    main()
