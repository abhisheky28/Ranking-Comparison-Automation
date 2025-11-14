# main.py (Final Production Version with Professional Email Templates)

import time
import random
import logging
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Imports for Email Notifications
import smtplib
import traceback
from email.mime.text import MIMEText

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from webdriver_manager.chrome import ChromeDriverManager

import config
import serp_selectors

# --- 1. LOGGING SETUP ---
log_file_path = os.path.join(config.PROJECT_ROOT, 'ranking_automation.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, mode='w'),
        logging.StreamHandler()
    ]
)

# --- EMAIL NOTIFICATION FUNCTION (No changes needed here) ---
def send_error_email(subject, body):
    if not config.ENABLE_EMAIL_NOTIFICATIONS:
        return
    if isinstance(config.RECIPIENT_EMAIL, str):
        recipients = [config.RECIPIENT_EMAIL]
    else:
        recipients = config.RECIPIENT_EMAIL
    logging.info(f"Preparing to send error email to: {', '.join(recipients)}")
    try:
        msg = MIMEText(body, 'plain') # Specify plain text
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

def human_like_typing(element, text):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.08, 0.15))

def find_and_type_in_search_box(driver, text):
    try:
        search_box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[name='q']")))
        human_like_typing(search_box, text)
        random_delay(1, 2)
        search_box.send_keys(Keys.RETURN)
        return True
    except TimeoutException:
        logging.error("Could not find the search box. Cannot perform search.")
        return False

# --- 3. SELENIUM WEBDRIVER SETUP ---
def get_humanlike_driver():
    logging.info("Initializing human-like Chrome WebDriver...")
    options = Options()
    random_user_agent = random.choice(config.USER_AGENTS)
    logging.info(f"Using User-Agent: {random_user_agent}")
    options.add_argument(f'user-agent={random_user_agent}')
    options.add_argument(f"--user-data-dir={config.CHROME_PROFILE_PATH}")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-infobars")
    #options.add_argument("--disable-extensions")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    print("!!! BROWSER IS PAUSED FOR 60 SECONDS. PLEASE LOG IN TO GOOGLE NOW IF NEEDED. !!!")
    time.sleep(2)
    
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

# --- 6. MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
#    logging.info("Attempting to terminate any running Chrome processes...")
#    os.system("taskkill /F /IM chrome.exe >nul 2>&1")
    time.sleep(3)

    logging.info("--- Starting Ranking Automation Script ---")
    
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
            
            driver.get(config.SEARCH_URL)
            random_delay(1, 3)
            
            if not find_and_type_in_search_box(driver, keyword):
                continue
            
            MAX_PAGES_TO_CHECK = 5
            ranks_found_so_far = {url: "Not Found" for url in urls_to_find}
            current_rank_offset = 0
            captcha_detected = False

            for page_num in range(1, MAX_PAGES_TO_CHECK + 1):
                logging.info(f"--- Scraping Page {page_num} for '{keyword}' ---")
                random_delay(2, 4)

                # --- NEW: INTELLIGENT CAPTCHA HANDLING LOGIC ---
                try:
                    # Check if the captcha iframe is present on the page
                    driver.find_element(By.CSS_SELECTOR, 'iframe[title="reCAPTCHA"]')
                    
                    # If found, start the waiting process for manual intervention
                    logging.warning(f"!!! CAPTCHA DETECTED for keyword '{keyword}'!!! Pausing for up to {config.CAPTCHA_WAIT_TIMEOUT / 60:.0f} minutes for manual intervention.")
                    
                    # Send an email notification asking for manual intervention
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

                    # Start the waiting loop
                    start_time = time.time()
                    captcha_solved = False
                    while time.time() - start_time < config.CAPTCHA_WAIT_TIMEOUT:
                        try:
                            # Keep checking if the captcha is still there
                            driver.find_element(By.CSS_SELECTOR, 'iframe[title="reCAPTCHA"]')
                            logging.info(f"Captcha still present. Waiting for {config.CAPTCHA_CHECK_INTERVAL} more seconds...")
                            time.sleep(config.CAPTCHA_CHECK_INTERVAL)
                        except NoSuchElementException:
                            # Captcha is gone! It was likely solved.
                            logging.info(">>> CAPTCHA SOLVED! Resuming script. <<<")
                            captcha_solved = True
                            break # Exit the waiting loop

                    # After the loop, check if it was solved or timed out
                    if not captcha_solved:
                        logging.error(f"CAPTCHA not solved within the {config.CAPTCHA_WAIT_TIMEOUT / 60:.0f} minute time limit. Aborting keyword '{keyword}'.")
                        
                        # Send a timeout notification email
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
                        
                        captcha_detected = True # Set flag to skip to the next keyword
                        break # Break from the page loop for this keyword
                
                except NoSuchElementException:
                    # No captcha found, proceed as normal
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
                    next_button = driver.find_element(By.CSS_SELECTOR, serp_selectors.NEXT_PAGE_BUTTON)
                    logging.info("Moving to next page...")
                    random_delay(1, 2)
                    next_button.click()
                    current_rank_offset += 10 
                except NoSuchElementException:
                    logging.info("No 'Next' button found. Reached the end of results.")
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
        
        # --- Human-Readable Crash Email with Technical Details ---
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
        logging.info("--- Ranking Automation Script Finished ---")