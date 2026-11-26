from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
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
    clean_text = text.lower()
    for remove_word in ['views', 'view', 'watching', 'การดู', 'ครั้ง', 'กำลังรับชม', 'คน']:
        clean_text = clean_text.replace(remove_word, '')
    clean_text = clean_text.strip()
    
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
        number_val = float(clean_text.replace(',', '').strip())
        return int(number_val * multiplier)
    except ValueError:
        return 0


def main():
    # รับ URL จากผู้ใช้
    target_url = input("Please enter YouTube Video URL (e.g., https://www.youtube.com/@ChannelName/videos): ")
    
    if not target_url:
        print("URL cannot be empty.")
        return

    print("URL received. Processing...")

    # ตั้งค่า Chrome Driver
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # สามารถเปิด headless ได้ถ้าต้องการ
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    try:
        print("Initializing Chrome driver...")
        driver = webdriver.Chrome(options=options)
        
        print(f"Opening {target_url}...")
        driver.get(target_url)
        
        # รอให้เว็บโหลด
        time.sleep(3)
        
        print("Scrolling to the end of the page... (This might take a while)")
        
        scroll_pause_time = 2.5 # เพิ่มเวลาพักนิดหน่อยเพื่อให้โหลดทัน
        last_height = driver.execute_script("return document.documentElement.scrollHeight")
        
        scroll_count = 0
        
        while True:
            # เลื่อนลงไปล่างสุด
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            
            # รอโหลด
            time.sleep(scroll_pause_time)
            
            # ตรวจสอบความสูงใหม่
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            
            scroll_count += 1
            print(f"Scrolled {scroll_count} times... Current height: {new_height}")

            if new_height == last_height:
                # ลองรอเพิ่มอีกนิดเผื่อเน็ตช้า
                time.sleep(5)
                new_height = driver.execute_script("return document.documentElement.scrollHeight")
                if new_height == last_height:
                    print("Reached end of page.")
                    break
            
            last_height = new_height
            
        print("Analyzing loaded videos...")
        
        # ใช้ XPath ดึงยอดวิวจาก yt-lockup-view-model โดยตรง
        view_xpath = '//*[@id="content"]/yt-lockup-view-model/div/div/yt-lockup-metadata-view-model/div[1]/div/yt-content-metadata-view-model/div/span[1]'
        view_elements = driver.find_elements(By.XPATH, view_xpath)
        
        print(f"Found {len(view_elements)} video view elements.")
        
        all_view_counts = []
        
        for i, el in enumerate(view_elements):
            try:
                view_text = el.text.strip()
                if not view_text:
                    continue
                
                # Debug: แสดง 5 รายการแรก
                if i < 5:
                    print(f"  [DEBUG #{i+1}] Raw text: '{view_text}'")
                
                v_val = parse_view_count(view_text)
                if v_val > 0:
                    all_view_counts.append(v_val)
                    
            except Exception as e:
                pass

        if all_view_counts:
            avg_views = sum(all_view_counts) / len(all_view_counts)
            print("=" * 50)
            print(f"Summary (All History)")
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
