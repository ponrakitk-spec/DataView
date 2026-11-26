from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import pickle
import os

def parse_facebook_view_count(text):
    """
    แปลงข้อความยอดวิว Facebook เป็นตัวเลข
    ตัวอย่าง: '1.2M', '500K', '100 com', 'Play'
    """
    if not text:
        return 0
    
    clean_text = text.upper().strip()
    clean_text = clean_text.replace('PLAYS', '').replace('PLAY', '').strip()
    
    multiplier = 1
    if 'K' in clean_text:
        multiplier = 1000
        clean_text = clean_text.replace('K', '')
    elif 'M' in clean_text:
        multiplier = 1000000
        clean_text = clean_text.replace('M', '')
    elif 'B' in clean_text:
        multiplier = 1000000000
        clean_text = clean_text.replace('B', '')
    # Thai Units
    elif 'พัน' in clean_text:
        multiplier = 1000
        clean_text = clean_text.replace('พัน', '')
    elif 'หมื่น' in clean_text:
        multiplier = 10000
        clean_text = clean_text.replace('หมื่น', '')
    elif 'แสน' in clean_text:
        multiplier = 100000
        clean_text = clean_text.replace('แสน', '')
    elif 'ล้าน' in clean_text:
        multiplier = 1000000
        clean_text = clean_text.replace('ล้าน', '')
        
    try:
        match = re.search(r'[\d\.]+', clean_text)
        if match:
            number_val = float(match.group())
            return int(number_val * multiplier)
        return 0
    except ValueError:
        return 0

def save_cookies(driver, filepath):
    try:
        with open(filepath, 'wb') as filehandler:
            pickle.dump(driver.get_cookies(), filehandler)
        print("cookies saved successfully.")
    except Exception as e:
        print(f"Error saving cookies: {e}")

def load_cookies(driver, filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'rb') as filehandler:
                cookies = pickle.load(filehandler)
                for cookie in cookies:
                    try:
                        driver.add_cookie(cookie)
                    except:
                        pass # บาง cookie อาจ set ไม่ได้ถ้า domain ไม่ตรง (ข้ามไป)
            print("Cookies loaded.")
            return True
    except Exception as e:
        print(f"Error loading cookies: {e}")
    return False

def main():
    target_url = input("Please enter Facebook Reels URL (e.g., https://www.facebook.com/page/reels/): ")
    
    if not target_url:
        print("URL cannot be empty.")
        return

    options = webdriver.ChromeOptions()
    prefs = {"profile.default_content_setting_values.notifications": 2}
    options.add_experimental_option("prefs", prefs)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled') 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = None
    cookie_file = "fb_cookies.pkl"

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # 1. ไปหน้าหลัก Facebook ก่อนเพื่อโหลด/สร้าง Cookie
        print("Opening Facebook...")
        driver.get("https://www.facebook.com")
        
        # 2. ลองโหลด Cookie เก่า
        load_cookies(driver, cookie_file)
        
        # 3. ไป URL เป้าหมาย
        print(f"Navigating to {target_url}...")
        driver.get(target_url)
        time.sleep(3)
        
        # 4. ให้ผู้ใช้ Log in ถ้าจำเป็น
        # 4. ใช้ Cookies ที่มีอยู่ ไม่ต้องรอ Log in
        print("Cookies loaded. Proceeding immediately...")
        time.sleep(5) # รอหน้าเว็บโหลดสักครู่
        
        # 5. บันทึก Cookie ล่าสุดเก็บไว้
        save_cookies(driver, cookie_file)
        
        # 6. เริ่ม Scroll
        print("Starting scroll process (Press Ctrl+C to stop manually if too long)...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_no_change = 5 
        no_change_count = 0
        
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(4)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                no_change_count += 1
                # print(f"  - No new content loaded ({no_change_count}/{max_no_change})")
                if no_change_count >= max_no_change:
                    print("Reached end of page or no more content loading.")
                    break
            else:
                no_change_count = 0
                scroll_attempts += 1
                print(f"  - Scrolled page {scroll_attempts} times...")
            
            last_height = new_height
            
            if scroll_attempts > 100: 
                print("Safety limit reached (100 scrolls). Proceeding to extraction.")
                break

        # 7. ดึงข้อมูล
        print("Extracting view counts...")
        
        # 1. Prioritize the User's specific XPath which proved effective
        # The user confirmed that the 'Exact User XPath' found the correct content as a block of text.
        # We will parse the text from these elements line-by-line.
        
        target_xpath = "//*[starts-with(@id, 'mount_0_0_')]/div/div[1]/div/div[3]/div/div/div[1]/div[1]/div/div/div[4]/div/div/div/div/div/div/div/div/div[3]"
        elements = driver.find_elements(By.XPATH, target_xpath)
        
        raw_candidates = []
        
        if elements:
            print(f"Found {len(elements)} container elements via Target XPath.")
            for el in elements:
                # The text might contain multiple lines e.g. "9.7 หมื่น\n2 หมื่น"
                text_block = el.text.strip()
                if text_block:
                    lines = text_block.split('\n')
                    for line in lines:
                        if line.strip():
                            raw_candidates.append(line.strip())
        else:
             print("Target XPath not found. Falling back to generalized search...")
             generalized_xpath = "//*[starts-with(@id, 'mount_0_0_')]/div/div[1]/div/div[3]/div/div/div[1]/div[1]/div/div/div[4]//div"
             elements = driver.find_elements(By.XPATH, generalized_xpath)
             for el in elements:
                 txt = el.text.strip()
                 if txt:
                      raw_candidates.append(txt)
                 lbl = el.get_attribute("aria-label")
                 if lbl:
                      raw_candidates.append(lbl)

        # Remove duplicates ONLY if we fell back to generalized search (because nested divs duplicate text).
        # But for the Target XPath (which returns distinct blocks), we trust the list order.
        # actually, to be safe, let's just process 'raw_candidates' as a list. 
        # But we must be careful not to double count if using generalized search.
        
        # Given the User's success with the Target XPath, we will rely on it.
        
        print(f"Collected {len(raw_candidates)} text lines for processing...")

        view_counts = []
        

        
        for text in raw_candidates:
            if len(text) > 50: continue # ยาวไปไม่ใช่ยอดวิวแน่ๆ
            
            # Pre-clean
            check_text = text.upper()
            
            # คำบ่งชี้ว่าเป็นยอดวิว (ถ้ามีคำเหล่านี้โอกาสใช่สูง)
            keywords = ['PLAYS', 'PLAY', 'VIEWS', 'VIEW', 'รับชม', 'ครั้ง', 'การดู', 'PLAY COUNT']
            has_keyword = any(k in check_text for k in keywords)
            
            # ลบคำออกเพื่อเช็คตัวเลข
            for word in keywords:
                check_text = check_text.replace(word, '')
            
            check_text = check_text.replace(',', '').replace('IS', '').strip() # ลบ IS เช่น "Play count is..."
            
            # Regex Check
            # Regex Check - Allow Thai characters in regex match for initial filter
            # match numbers, dots/commas, and optional units (K/M/B/Thai)
            if re.search(r'[\d\.,]+', check_text):
                val = parse_facebook_view_count(text)
                
                # Logic กรองเข้มข้น:
                # 1. ถ้ามี K/M/B -> ใช่แน่นอน
                # 2. ถ้าไม่มีหน่วย -> ต้องมี keyword ปรากฏใน text ต้นฉบับ หรือ ค่าต้องเยอะมากพอ
                # 3. ต้องไม่น้อยกว่า 100 (เลี่ยงเลขนาที/ลำดับ)
                
                is_valid = False
                if 'K' in check_text or 'M' in check_text or 'B' in check_text:
                    is_valid = True
                elif 'พัน' in text or 'หมื่น' in text or 'แสน' in text or 'ล้าน' in text:
                    is_valid = True
                elif has_keyword and val > 0:
                     is_valid = True
                elif val > 100: # ถ้าเป็นตัวเลขเฉยๆ ให้รับถ้ามากกว่า 100 (เผื่อยอดยังน้อย)
                     is_valid = True
                     
                if is_valid:
                    view_counts.append(val)
                    print(f" - Found view candidate: '{text}' -> {val:,.0f}")

        if view_counts:
            # กรองค่า 0
            view_counts = [v for v in view_counts if v > 0]


        if view_counts:
            print(f"\nFound {len(view_counts)} items.")
            average_views = sum(view_counts) / len(view_counts)
            print("-" * 30)
            print(f"Total Videos Processed: {len(view_counts)}")
            print(f"Average Views: {average_views:,.2f}")
            print("-" * 30)
        else:
            print("No view counts could be extracted.")

    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
