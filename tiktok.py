from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time
import re
import json

def main():
    # รับ URL จากผู้ใช้
    target_url = input("Please enter TikTok Profile URL (e.g., https://www.tiktok.com/@username): ")
    
    if not target_url:
        print("URL cannot be empty.")
        return

    print("URL received. Processing...")

    # ตั้งค่า Chrome Driver ให้สามารถอ่าน Performance Logs (Network) ได้
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled') 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # สำคัญ: เปิดใช้งาน Performance Logging
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = None
    try:
        print("Initializing Chrome driver...")
        driver = webdriver.Chrome(options=options)
        
        print(f"Opening {target_url}...")
        driver.get(target_url)
        
        # รอให้เว็บโหลด
        time.sleep(5)
        
        # Scroll เพื่อกระตุ้นให้เกิดการเรียก API (api/post/item_list)
        print("Scrolling to trigger API calls until the bottom of the page...")

        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempt = 0
        max_attempts = 1000  # safety limit to avoid infinite loops

        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                # ถ้าไม่มีการเพิ่มความสูง แปลว่าเราอยู่ที่ด้านล่างสุดแล้ว
                break

            last_height = new_height
            scroll_attempt += 1
            if scroll_attempt >= max_attempts:
                print(f"Reached max scroll attempts ({max_attempts}), stopping.")
                break

        print("Processing Network Logs...")
        
        # ดึง Logs ทั้งหมด
        logs = driver.get_log('performance')
        
        view_counts = []
        found_api_calls = 0

        for entry in logs:
            try:
                log_message = json.loads(entry['message'])
                message = log_message['message']
                
                # กรองเฉพาะ Network.responseReceived
                if message['method'] == 'Network.responseReceived':
                    request_url = message['params']['response']['url']
                    
                    # ตรวจสอบว่าเป็น API ที่เราต้องการหรือไม่
                    # URL ตัวอย่าง: https://www.tiktok.com/api/post/item_list/?...
                    if 'api/post/item_list' in request_url:
                        found_api_calls += 1
                        request_id = message['params']['requestId']
                        
                        try:
                            # ใช้ CDP Command ดึง Response Body
                            response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                            body_content = response_body['body']
                            
                            # Parse JSON
                            data = json.loads(body_content)
                            
                            # ดึงรายการ Video (itemList)
                            if 'itemList' in data:
                                for item in data['itemList']:
                                    # เช็คยอดวิวจาก stats.playCount
                                    if 'stats' in item and 'playCount' in item['stats']:
                                        views = item['stats']['playCount']
                                        view_counts.append(views)
                                        print(f" - Found video views: {views:,.0f}")
                        except Exception as e:
                            # บางครั้ง Request ID อาจจะหมดอายุถ้าผ่านไปนาน
                            # print(f"Could not get body for {request_url}: {e}")
                            pass
                            
            except Exception as e:
                pass

        if not view_counts:
            print("No view counts found in API logs. Trying fallback to scraping...")
            # Fallback (เผื่อ API ไม่ถูกเรียกหรือดึงไม่ได้) - ใช้วิธีเดิมแต่เป็นส่วนเสริม
            try:
                elements = driver.find_elements(By.XPATH, "//*[text()]")
                for element in elements:
                    text = element.text.strip()
                    if text and re.fullmatch(r'\d+(\.\d+)?[KMB]?', text, re.IGNORECASE):
                         # แปลง text เป็นตัวเลข code เก่า
                         multiplier = 1
                         clean_text = text.upper().replace('K', '').replace('M', '').replace('B', '')
                         if 'K' in text.upper(): multiplier = 1000
                         elif 'M' in text.upper(): multiplier = 1000000
                         elif 'B' in text.upper(): multiplier = 1000000000
                         try:
                             val = int(float(clean_text) * multiplier)
                             view_counts.append(val)
                             print(f" - Found video views (Scraped): {val:,.0f}")
                         except: pass
            except: pass

        if view_counts:
            print(f"\nFound {len(view_counts)} videos from API/Scraping.")
            average_views = sum(view_counts) / len(view_counts)
            max_views = max(view_counts)
            print("-" * 30)
            print(f"Total Videos Processed: {len(view_counts)}")
            print(f"Average Views: {average_views:,.2f}")
            print(f"Max Views: {max_views:,.0f}")
            print("-" * 30)
        else:
            print("No data extracted.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
