from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import time
import json
import datetime


def is_within_last_3_months(create_time):
    # create_time ใน TikTok API มักเป็น timestamp วินาที
    try:
        create_ts = int(create_time)
    except Exception:
        return False

    create_dt = datetime.datetime.fromtimestamp(create_ts, datetime.timezone.utc)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
    return create_dt >= cutoff


def parse_view_count(text):
    # ฟังก์ชันแปลงข้อความเป็นตัวเลข (เช่น 1.2K -> 1200)
    try:
        text = text.strip().upper()
        multiplier = 1
        if text.endswith('K'):
            multiplier = 1000
            text = text[:-1]
        elif text.endswith('M'):
            multiplier = 1000000
            text = text[:-1]
        elif text.endswith('B'):
            multiplier = 1000000000
            text = text[:-1]

        return int(float(text) * multiplier)
    except Exception:
        return None


def main():
    target_url = input("Please enter TikTok Profile URL (e.g., https://www.tiktok.com/@username):")
    if not target_url:
        print("URL cannot be empty.")
        return

    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = None
    try:
        driver = webdriver.Chrome(options=options)

        print(f"Opening {target_url}...")
        driver.get(target_url)
        time.sleep(5)

        print("Scrolling profile to load posts (max 90 times or until 3-month boundary)")
        scrolls = 0
        last_height = driver.execute_script("return document.body.scrollHeight")
        all_logs = []
        processed_request_ids = set()
        found_older_than_3_months = False

        while scrolls < 90 and not found_older_than_3_months:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(4)  # เพิ่มเวลาการรอโหลดข้อมูลให้ช้าลง
            new_height = driver.execute_script("return document.body.scrollHeight")

            # เก็บ log การโหลดใหม่สำหรับตรวจ 3-month boundary
            new_logs = driver.get_log('performance')
            all_logs.extend(new_logs)

            for entry in new_logs:
                try:
                    log_message = json.loads(entry['message'])
                    message = log_message.get('message', {})
                    if message.get('method') != 'Network.responseReceived':
                        continue

                    response = message['params'].get('response', {})
                    request_url = response.get('url', '')
                    if 'api/post/item_list' not in request_url:
                        continue

                    request_id = message['params'].get('requestId')
                    if not request_id or request_id in processed_request_ids:
                        continue

                    processed_request_ids.add(request_id)
                    try:
                        response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                        body_content = response_body.get('body', '')
                        data = json.loads(body_content)
                    except Exception:
                        continue

                    items_list = data.get('itemList', [])
                    if items_list:
                        # เช็คแค่วิดีโอตัวสุดท้ายในชุดข้อมูลเพื่อเลี่ยงปัญหาวิดีโอที่โดน 'Pinned' (ปักหมุด)
                        last_item = items_list[-1]
                        create_time = last_item.get('createTime') or last_item.get('create_time')
                        if create_time and not is_within_last_3_months(create_time):
                            found_older_than_3_months = True

                    if found_older_than_3_months:
                        break
                except Exception:
                    continue

            if new_height == last_height:
                break
            last_height = new_height
            scrolls += 1

        # เก็บ log ตอนจบอีกครั้งเผื่อมี request ที่ยังไม่ถูกอ่าน
        final_logs = driver.get_log('performance')
        all_logs.extend(final_logs)

        print(f"Scrolled {scrolls} times, found older-than-3-months={found_older_than_3_months}, collecting 3-month items")

        logs = all_logs
        view_counts = []
        seen_post_ids = set()
        total_count = 0
        in_range_count = 0

        for entry in logs:
            try:
                log_message = json.loads(entry['message'])
                message = log_message['message']
                if message.get('method') != 'Network.responseReceived':
                    continue

                response = message['params'].get('response', {})
                request_url = response.get('url', '')
                if 'api/post/item_list' not in request_url:
                    continue

                request_id = message['params'].get('requestId')
                if not request_id:
                    continue

                try:
                    response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                    body_content = response_body.get('body', '')
                    data = json.loads(body_content)
                except Exception:
                    continue

                items = data.get('itemList', [])
                for item in items:
                    post_id = item.get('id')
                    if not post_id or post_id in seen_post_ids:
                        continue
                    seen_post_ids.add(post_id)
                    total_count += 1
                    create_time = item.get('createTime') or item.get('create_time')

                    if create_time and is_within_last_3_months(create_time):
                        in_range_count += 1
                        stats = item.get('stats', {})
                        play_count = stats.get('playCount')
                        if play_count is not None:
                            view_counts.append(int(play_count))
                            post_date = datetime.datetime.fromtimestamp(int(create_time), datetime.timezone.utc).date()
                            print(f" - {post_date} views={play_count}")
                    else:
                        # skip item older than 3 months
                        continue

            except Exception:
                continue

        if view_counts:
            average = sum(view_counts) / len(view_counts)
            print("\n=== 3-month TikTok stats ===")
            print(f"Total posts in logs (all): {total_count}")
            print(f"Total posts in last 3 months (API): {in_range_count}")
            print(f"Counted view values: {len(view_counts)}")
            print(f"Average views (last 3 months): {average:,.2f}")
            print("==========================")
        else:
            print("No view count data collected.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if driver:
            driver.quit()


if __name__ == '__main__':
    main()
