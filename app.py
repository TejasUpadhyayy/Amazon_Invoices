import time
import os
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

st.title("📦 Amazon Invoice & Order Summary Downloader")
st.write("This app logs into Amazon, downloads invoice PDFs, and saves them to your selected directory.")

# User inputs
email = st.text_input("📧 Enter your Amazon email:", type="default")
password = st.text_input("🔑 Enter your Amazon password:", type="password")
orders_url = st.text_input("🔗 Enter Amazon orders list URL:")
download_dir = st.text_input("📁 Enter directory to save invoices:", value=r"/tmp/invoices")

if st.button("Start Downloading Invoices"):
    if not email or not password or not orders_url or not download_dir:
        st.error("❌ Please fill all fields!")
    else:
        st.info("🚀 Starting invoice download process...")

        # Set up headless Chrome options
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920x1080")

        # Configure Chrome to download PDFs automatically
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)

        # Launch browser
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        try:
            st.info("🔄 Navigating to Amazon Orders Page...")
            driver.get(orders_url)

            # Login if required
            if "signin" in driver.current_url:
                st.warning("🔒 Amazon login required. Logging in...")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ap_email"))).send_keys(email)
                driver.find_element(By.ID, "continue").click()
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ap_password"))).send_keys(password)
                driver.find_element(By.ID, "signInSubmit").click()
                time.sleep(5)
                st.success("✅ Successfully logged in!")

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="a-page"]/section/div/li'))
            )
            st.info("✅ Orders list loaded successfully.")

            # Process each order
            for i in range(5):  # Process top 5 orders
                try:
                    driver.get(orders_url)
                    time.sleep(5)  # Wait for page to load

                    order_ids_elements = driver.find_elements(By.XPATH, '//*[@id="a-page"]/section/div/li/div/div/div[1]/div/div/div/h5/div[2]/div[1]/div/span[2]')
                    invoice_links_elements = driver.find_elements(By.XPATH, '//*[@id="a-page"]/section/div/li/div/div/div[1]/div/div/div/h5/div[2]/div[2]/div/ul/li[2]/span/a')

                    if i >= len(order_ids_elements) or i >= len(invoice_links_elements):
                        st.warning("⚠ Not enough orders found.")
                        break

                    order_id = order_ids_elements[i].text
                    invoice_link_element = invoice_links_elements[i]

                    st.info(f"🆔 Clicking Invoice for Order {i+1}: {order_id}")
                    driver.execute_script("arguments[0].click();", invoice_link_element)
                    time.sleep(3)

                    printable_order_summary_link = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//div[contains(@id, 'a-popover-content')]/ul/li/span/a"))
                    )
                    st.info(f"📑 Clicking Printable Order Summary for Order {order_id}")
                    driver.execute_script("arguments[0].click();", printable_order_summary_link)
                    time.sleep(5)

                    st.success(f"✅ Invoice Downloaded for Order {order_id}!")

                except Exception as e:
                    st.error(f"❌ Error processing Order {i+1}: {e}")

        finally:
            time.sleep(5)
            if driver:
                driver.quit()
                st.success("✅ Process Completed & Browser Closed!")

