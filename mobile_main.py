# main.py (Final, Full-Featured Mobile Ranking Scraper)

import time
import random
import logging
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse

# Imports for Email Notifications
import smtplib
import traceback
from email.mime.text import MIMEText

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from webdriver_manager.chrome import ChromeDriverManager

import config
import serp_selectors # Using the dedicated selectors file

# --- 1. LOGGING SETUP ---
log_file_path = os.path.join(config.PROJECT_ROOT, 'mobile_ranking_automation.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, mode='w'),
        logging.StreamHandler()
    ]
)

# --- EMAIL NOTIFICATION FUNCTION (Full Version) ---
def send_error_email(subject, body):
    if not config.ENABLE_EMAIL_NOTIFICATIONS:
        return
    recipients = config.RECIPIENT_EMAIL if isinstance(config.RECIPIENT_EMAIL, list) else [config.RECIPIENT_EMAIL]
    logging.info(f"Preparing to send error email to: {', '.join(recipients)}")
    try:
        msg = MIMEText(body, 'plain')
        msg['Subject'] = subject
        msg['From'] = config.SENDER_EMAIL
        msg['To'] = ", ".join(recipients)
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
            server.sendmail(config.SENDER_EMAIL, recipients, msg.as_string())
            logging.info("Error email sent successfully.")
    except Exception as e:
        logging.error(f"CRITICAL: FAILED TO SEND ERROR EMAIL. Error: {e}")

# --- 2. HUMAN BEHAVIOR FUNCTIONS ---
def random_delay(min_seconds=1, max_seconds=3):
    time.sleep(random.uniform(min_seconds, max_seconds))

# --- 3. SELENIUM WEBDRIVER SETUP (MODIFIED FOR MOBILE EMULATION) ---
def get_humanlike_driver():
    logging.info("Initializing MOBILE Chrome WebDriver (Emulating Pixel 5)...")
    
    # Define the device properties for a Google Pixel 5
    mobile_emulation = {
        "deviceMetrics": { "width": 393, "height": 851, "pixelRatio": 3.0 },
        "userAgent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36"
    }
    
    options = Options()
    # Enable mobile emulation
    options.add_experimental_option("mobileEmulation", mobile_emulation)
    
    # Standard options from your original robust script
    options.add_argument(f"--user-data-dir={config.CHROME_PROFILE_PATH}")
    options.add_argument("--incognito")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    print("!!! BROWSER LAUNCHED IN MOBILE EMULATION MODE. SCRIPT WILL START SHORTLY. !!!")
    time.sleep(5)
    
    driver.set_page_load_timeout(45)
    return driver

# --- 4. GOOGLE SHEETS FUNCTIONS ---
def connect_to_gsheet():
    logging.info(f"Connecting to Google Sheet: '{config.SHEET_NAME}'")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(config.GCP_CREDENTIALS_PATH, scope)
    client = gspread.authorize(creds)
    sheet = client.open(config.SHEET_NAME).worksheet(config.WORKSHEET_NAME)
    logging.info("Successfully connected to Google Sheet.")
    return sheet

def get_data_from_sheet(sheet):
    logging.info("Fetching data from the worksheet...")
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    df['original_index'] = df.index + 2
    logging.info(f"Successfully fetched {len(df)} keywords.")
    return df

# --- 5. CORE SCRAPING LOGIC ---
def find_competitor_ranks(driver, competitor_urls, rank_offset=0):
    ranks = {url: "Not Found" for url in competitor_urls if url}
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, serp_selectors.RESULT_CONTAINER)))
        all_potential_blocks = driver.find_elements(By.CSS_SELECTOR, serp_selectors.RESULT_CONTAINER)
        clean_organic_results = []
        for block in all_potential_blocks:
            try:
                if block.find_elements(By.CSS_SELECTOR, "[data-text-ad]"): continue
                h3_element = block.find_element(By.CSS_SELECTOR, "h3")
                if not h3_element.text.strip(): continue
                clean_organic_results.append(block)
            except NoSuchElementException:
                continue
        for rank, organic_block in enumerate(clean_organic_results, start=1 + rank_offset):
            try:
                link_element = organic_block.find_element(By.CSS_SELECTOR, serp_selectors.LINK_CONTAINER)
                url = link_element.get_attribute('href')
                if not url: continue
                for competitor_url in ranks.keys():
                    if competitor_url in url and ranks[competitor_url] == "Not Found":
                        ranks[competitor_url] = rank
            except NoSuchElementException:
                continue
    except Exception as e:
        logging.error(f"An error occurred during scraping on this page: {e}")
    return ranks

# --- 6. MAIN EXECUTION BLOCK (Full Version with All Logic) ---
if __name__ == "__main__":
#    logging.info("Attempting to terminate any running Chrome processes...")
#    os.system("taskkill /F /IM chrome.exe >nul 2>&1")
    time.sleep(3)

    logging.info("--- Starting MOBILE Ranking Automation Script ---")
    
    driver = None
    try:
        worksheet = connect_to_gsheet()
        df = get_data_from_sheet(worksheet)
        
        indices_to_process = list(df.index)
        random.shuffle(indices_to_process)
        indices_to_process = indices_to_process[:config.KEYWORDS_PER_BATCH]
        logging.info(f"Processing a batch of {len(indices_to_process)} keywords.")

        driver = get_humanlike_driver()

        for i, index in enumerate(indices_to_process):
            row = df.loc[index]
            keyword = row['Keyword']
            original_row_index = row['original_index']
            logging.info(f"\n--- Processing keyword {i+1}/{len(indices_to_process)}: '{keyword}' ---")
            
            competitors = {'ICICI': {'url': row['ICICI URL'], 'col': 6}, 'Kotak': {'url': row['Kotak URL'], 'col': 7}, 'HDFC': {'url': row['HDFC URL'], 'col': 8}, 'SBI': {'url': row['SBI URL'], 'col': 9}}
            urls_to_find = [comp['url'] for comp in competitors.values() if comp['url']]
            
            if not urls_to_find:
                logging.warning(f"No URLs for '{keyword}'. Skipping.")
                continue
            
            encoded_keyword = urllib.parse.quote_plus(keyword)
            search_url = f"{config.SEARCH_URL}/search?q={encoded_keyword}&gl={config.SEARCH_COUNTRY_CODE}&hl=en"
            
            logging.info(f"Navigating to geo-targeted URL: {search_url}")
            driver.get(search_url)
            
            MAX_PAGES_TO_CHECK = 5
            ranks_found_so_far = {url: "Not Found" for url in urls_to_find}
            current_rank_offset = 0
            captcha_detected = False

            for page_num in range(1, MAX_PAGES_TO_CHECK + 1):
                logging.info(f"--- Scraping Page {page_num} for '{keyword}' ---")
                random_delay(2, 4)

                # --- FULL CAPTCHA HANDLING LOGIC (RESTORED) ---
                try:
                    driver.find_element(By.CSS_SELECTOR, 'iframe[title="reCAPTCHA"]')
                    logging.warning(f"!!! CAPTCHA DETECTED for keyword '{keyword}'!!! Pausing for up to {config.CAPTCHA_WAIT_TIMEOUT / 60:.0f} minutes for manual intervention.")
                    
                    email_subject = f"ACTION REQUIRED: Ranking Scraper Paused by CAPTCHA"
                    email_body = f"""
Hello,
The automated Ranking Scraper has been paused by a Google security check (CAPTCHA) and requires your immediate attention.
Keyword being processed: "{keyword}"
Please find the browser window opened by the script and solve the CAPTCHA puzzle.
The script will wait for up to {config.CAPTCHA_WAIT_TIMEOUT / 60:.0f} minutes. If the CAPTCHA is not solved within this time, it will skip this keyword and continue.
- Automated System
"""
                    send_error_email(email_subject, email_body)

                    start_time = time.time()
                    captcha_solved = False
                    while time.time() - start_time < config.CAPTCHA_WAIT_TIMEOUT:
                        try:
                            driver.find_element(By.CSS_SELECTOR, 'iframe[title="reCAPTCHA"]')
                            logging.info(f"Captcha still present. Waiting for {config.CAPTCHA_CHECK_INTERVAL} more seconds...")
                            time.sleep(config.CAPTCHA_CHECK_INTERVAL)
                        except NoSuchElementException:
                            logging.info(">>> CAPTCHA SOLVED! Resuming script. <<<")
                            captcha_solved = True
                            break

                    if not captcha_solved:
                        logging.error(f"CAPTCHA not solved within the {config.CAPTCHA_WAIT_TIMEOUT / 60:.0f} minute time limit. Aborting keyword '{keyword}'.")
                        email_subject_timeout = "Ranking Scraper Alert: CAPTCHA Timed Out"
                        email_body_timeout = f"""
Hello,
This is an alert that the Ranking Scraper, which was paused for a CAPTCHA, has timed out.
Keyword: "{keyword}"
The CAPTCHA was not solved within the {config.CAPTCHA_WAIT_TIMEOUT / 60:.0f}-minute time limit. The script has now aborted this keyword and will proceed with its run.
No action is required. This is an informational alert.
- Automated System
"""
                        send_error_email(email_subject_timeout, email_body_timeout)
                        captcha_detected = True
                        break
                
                except NoSuchElementException:
                    pass
                
                page_ranks = find_competitor_ranks(driver, urls_to_find, current_rank_offset)

                for url, rank in page_ranks.items():
                    if rank != "Not Found" and ranks_found_so_far[url] == "Not Found":
                        ranks_found_so_far[url] = rank
                        logging.info(f"SUCCESS: Found '{url}' at rank {rank} on page {page_num}")

                if all(rank != "Not Found" for rank in ranks_found_so_far.values()):
                    logging.info("All competitors found. Moving to next keyword.")
                    break

                try:
                    # --- THIS IS THE KEY CHANGE FOR MOBILE PAGINATION ---
                    next_button = driver.find_element(By.CSS_SELECTOR, serp_selectors.NEXT_PAGE_BUTTON)
                    logging.info("Moving to next page (clicking 'More results')...")
                    random_delay(1, 2)
                    driver.execute_script("arguments[0].click();", next_button)
                    current_rank_offset += 10 
                except NoSuchElementException:
                    logging.info("No 'More results' button found. Reached the end of results.")
                    break
            
            if not captcha_detected:
                logging.info(f"Finished scraping for '{keyword}'. Final ranks: {ranks_found_so_far}")
                for name, data in competitors.items():
                    if data['url']:
                        rank_to_write = ranks_found_so_far.get(data['url'], "Not Found")
                        worksheet.update_cell(original_row_index, data['col'], str(rank_to_write))
            
            time.sleep(random.uniform(5, 10))
            
    except Exception as e:
        logging.critical(f"A critical, unhandled error occurred: {e}", exc_info=True)
        
        # --- FULL CRASH REPORTING EMAIL LOGIC (RESTORED) ---
        email_subject = "Ranking Scraper Alert: Script CRASHED"
        technical_details = traceback.format_exc()
        email_body = f"""
Hello,
The automated Ranking Scraper has stopped due to an unexpected technical error. The script did not complete its run.
The technical team has been notified with the details below.
No action is required from you at this time.
- Automated System
----------------------------------------------------
--- TECHNICAL DETAILS FOR DEBUGGING ---
----------------------------------------------------
{technical_details}
"""
        send_error_email(email_subject, email_body)
        
    finally:
        if driver:
            logging.info("Closing WebDriver.")
            driver.quit()
        logging.info("--- MOBILE Ranking Automation Script Finished ---")