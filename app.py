import time
import os
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import platform
import tempfile

st.title("📦 Amazon Invoice & Order Summary Downloader")
st.write("This app logs into Amazon, downloads invoice PDFs, and saves them to your selected directory.")

# Create a temporary directory as fallback
temp_dir = tempfile.mkdtemp()
st.sidebar.info(f"If you encounter permission issues, try using this temporary directory: {temp_dir}")

# User inputs
email = st.text_input("📧 Enter your Amazon email:", type="default")
password = st.text_input("🔑 Enter your Amazon password:", type="password")
orders_url = st.text_input("🔗 Enter Amazon orders list URL:")
download_dir = st.text_input("📁 Enter directory to save invoices:", value=os.path.join(os.path.expanduser("~"), "downloads"))

# Ensure download directory exists
if not os.path.exists(download_dir):
    try:
        os.makedirs(download_dir, exist_ok=True)
        st.success(f"Created download directory: {download_dir}")
    except Exception as e:
        st.error(f"Failed to create download directory: {e}")
        st.info("Trying alternative download locations...")
        
        # Try alternative locations
        alternative_locations = [
            os.path.join(os.getcwd(), "downloads"),  # Current working directory
            "/tmp/downloads",  # /tmp is usually writable
            os.path.join(os.path.expanduser("~"), ".streamlit", "downloads")  # Streamlit config directory
        ]
        
        for location in alternative_locations:
            try:
                os.makedirs(location, exist_ok=True)
                download_dir = location
                st.success(f"Created alternative download directory: {download_dir}")
                break
            except Exception as alt_e:
                st.warning(f"Could not create directory at {location}: {alt_e}")

if st.button("Start Downloading Invoices"):
    if not email or not password or not orders_url or not download_dir:
        st.error("❌ Please fill all fields!")
    else:
        st.info("🚀 Starting invoice download process...")

        # Set up headless Chrome options
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless=new")  # Updated headless mode syntax
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920x1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Configure Chrome to download PDFs automatically
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_settings.popups": 0,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Bypass CloudFlare and other detection methods
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        try:
            # Improved WebDriver initialization with appropriate error handling
            st.info("🔄 Initializing Chrome WebDriver...")
            
            try:
                # Try using webdriver_manager
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                st.warning(f"ChromeDriverManager failed: {e}. Trying alternative approach...")
                
                # Alternative approach for Streamlit Cloud
                system = platform.system().lower()
                if system == "linux":
                    # On Linux/Streamlit Cloud, try using system Chrome
                    driver = webdriver.Chrome(options=chrome_options)
                else:
                    # On other systems, try a direct path
                    st.error(f"Could not initialize Chrome WebDriver on {system}. Please check Chrome and ChromeDriver installation.")
                    st.stop()

            st.success("✅ WebDriver initialized successfully!")
            
            # Set page load timeout
            driver.set_page_load_timeout(30)
            
            st.info("🔄 Navigating to Amazon Orders Page...")
            driver.get(orders_url)

            # Login if required
            if "signin" in driver.current_url:
                st.warning("🔒 Amazon login required. Logging in...")
                try:
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "ap_email"))).send_keys(email)
                    driver.find_element(By.ID, "continue").click()
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "ap_password"))).send_keys(password)
                    driver.find_element(By.ID, "signInSubmit").click()
                    
                    # Wait for login to complete
                    time.sleep(10)
                    
                    # Check if we need to solve a CAPTCHA
                    if "captcha" in driver.page_source.lower():
                        st.error("⚠️ CAPTCHA detected. Manual intervention required.")
                        st.warning("This app can't solve CAPTCHAs automatically. Please try again later or use a different method.")
                        st.stop()
                        
                    st.success("✅ Successfully logged in!")
                except Exception as login_error:
                    st.error(f"❌ Login failed: {login_error}")
                    st.stop()

            # Wait for orders list to load
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="a-page"]/section/div/li'))
                )
                st.info("✅ Orders list loaded successfully.")
            except Exception as e:
                st.error(f"❌ Failed to load orders list: {e}")
                st.write("Page source (for debugging):")
                st.code(driver.page_source[:1000] + "...")  # Show first 1000 chars for debugging
                st.stop()

            # Create directory for order count
            order_count = 0

            # Process each order
            for i in range(5):  # Process top 5 orders
                try:
                    driver.get(orders_url)
                    time.sleep(8)  # Wait for page to load

                    # Capture screenshot for debugging
                    screenshot_path = os.path.join(download_dir, f"debug_screenshot_{i}.png")
                    driver.save_screenshot(screenshot_path)
                    st.image(screenshot_path, caption=f"Debug Screenshot for Order {i+1}", width=300)

                    # Use more robust selectors
                    order_ids_elements = driver.find_elements(By.XPATH, '//span[contains(@class, "order-id-text") or contains(@class, "order-id")]')
                    invoice_links_elements = driver.find_elements(By.XPATH, '//a[contains(text(), "Invoice") or contains(@href, "invoice")]')

                    if i >= len(order_ids_elements) or i >= len(invoice_links_elements):
                        st.warning(f"⚠ Not enough orders found. Found {len(order_ids_elements)} order IDs and {len(invoice_links_elements)} invoice links.")
                        break

                    order_id = order_ids_elements[i].text.strip()
                    invoice_link_element = invoice_links_elements[i]

                    st.info(f"🆔 Clicking Invoice for Order {i+1}: {order_id}")
                    driver.execute_script("arguments[0].scrollIntoView(true);", invoice_link_element)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", invoice_link_element)
                    time.sleep(5)

                    # Look for the printable order summary link
                    try:
                        # Try multiple possible XPaths
                        xpaths = [
                            "//div[contains(@id, 'a-popover-content')]/ul/li/span/a",
                            "//a[contains(text(), 'Printable Order Summary')]",
                            "//a[contains(@href, 'print-summary')]"
                        ]
                        
                        printable_link_found = False
                        for xpath in xpaths:
                            try:
                                printable_order_summary_link = WebDriverWait(driver, 8).until(
                                    EC.element_to_be_clickable((By.XPATH, xpath))
                                )
                                printable_link_found = True
                                break
                            except:
                                continue
                                
                        if not printable_link_found:
                            st.warning(f"⚠️ Could not find Printable Order Summary link for Order {order_id}. Trying next order.")
                            continue
                            
                        st.info(f"📑 Clicking Printable Order Summary for Order {order_id}")
                        driver.execute_script("arguments[0].click();", printable_order_summary_link)
                        
                        # Switch to new tab if opened
                        if len(driver.window_handles) > 1:
                            driver.switch_to.window(driver.window_handles[1])
                        
                        time.sleep(8)  # Wait for PDF to download
                        
                        # Check if PDF is available in download directory
                        files = os.listdir(download_dir)
                        pdf_files = [f for f in files if f.endswith('.pdf')]
                        if pdf_files:
                            st.success(f"✅ Invoice Downloaded for Order {order_id}! PDF files in directory: {', '.join(pdf_files)}")
                            order_count += 1
                        else:
                            st.warning(f"⚠️ No PDF files found in download directory for Order {order_id}")
                        
                        # Close tab and switch back to main window if needed
                        if len(driver.window_handles) > 1:
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                            
                    except Exception as e:
                        st.error(f"❌ Error getting printable summary for Order {order_id}: {e}")

                except Exception as e:
                    st.error(f"❌ Error processing Order {i+1}: {e}")

            st.success(f"✅ Process Completed! Downloaded {order_count} out of {min(5, len(order_ids_elements))} invoices.")

        except Exception as e:
            st.error(f"❌ An error occurred: {e}")
            
        finally:
            time.sleep(5)
            if 'driver' in locals():
                driver.quit()
                st.success("✅ Browser Closed!")
