import os
import time
import streamlit as st
import tempfile
import json
import subprocess
import sys
import platform
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from bs4 import BeautifulSoup
import re

st.set_page_config(page_title="Amazon Invoice Downloader", page_icon="📦")

st.title("📦 Automated Amazon Invoice Downloader")
st.write("This app logs in to Amazon, captures your cookies, and downloads invoice PDFs.")

# Create a temporary directory as fallback
temp_dir = tempfile.mkdtemp()
st.sidebar.info(f"Temporary directory: {temp_dir}")

# User inputs
with st.expander("📝 Amazon Login Information", expanded=True):
    email = st.text_input("📧 Amazon Email:", type="default")
    password = st.text_input("🔑 Amazon Password:", type="password")
    
    # Handle 2FA if needed
    if 'needs_2fa' in st.session_state and st.session_state.needs_2fa:
        verification_code = st.text_input("🔐 Enter verification code sent to your device:")
    
    st.info("Your login information is only used locally to authenticate with Amazon. Nothing is stored or sent elsewhere.")

with st.expander("📁 Download Settings", expanded=True):
    orders_url = st.text_input("🔗 Amazon Orders URL:", 
                              value="https://www.amazon.com/gp/your-account/order-history")
    download_dir = st.text_input("📁 Directory to save invoices:", 
                                value=os.path.join(os.path.expanduser("~"), "amazon_invoices"))

# Ensure download directory exists
if download_dir and not os.path.exists(download_dir):
    try:
        os.makedirs(download_dir, exist_ok=True)
        st.success(f"Created download directory: {download_dir}")
    except Exception as e:
        st.error(f"Failed to create download directory: {e}")
        download_dir = temp_dir
        st.info(f"Using temporary directory instead: {download_dir}")

# Function to extract cookies using Selenium
def extract_amazon_cookies(email, password, verification_code=None):
    st.info("🚀 Launching browser to extract cookies...")
    
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Try to avoid detection
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    try:
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        
        # Navigate to Amazon login
        driver.get("https://www.amazon.com/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=usflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
        
        # Handle email
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "ap_email"))
            )
            email_field.send_keys(email)
            
            continue_button = driver.find_element(By.ID, "continue")
            continue_button.click()
        except Exception as e:
            st.error(f"Error entering email: {e}")
            driver.quit()
            return None, f"Error entering email: {e}"
        
        # Handle password
        try:
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "ap_password"))
            )
            password_field.send_keys(password)
            
            signin_button = driver.find_element(By.ID, "signInSubmit")
            signin_button.click()
        except Exception as e:
            st.error(f"Error entering password: {e}")
            driver.quit()
            return None, f"Error entering password: {e}"
        
        # Check if 2FA is needed
        time.sleep(3)  # Allow page to load
        
        page_source = driver.page_source.lower()
        if verification_code and ('verification' in page_source or 'two-factor' in page_source or 'otp' in page_source):
            try:
                # Find verification code input field - try different possible IDs and types
                verif_field = None
                
                # Try different possible field identifiers
                for field_id in ['auth-mfa-otpcode', 'ap_verification_code', 'auth-mfa-code', 'cvf-input-code']:
                    try:
                        verif_field = driver.find_element(By.ID, field_id)
                        break
                    except:
                        pass
                
                # If not found by ID, try by attribute
                if not verif_field:
                    try:
                        verif_field = driver.find_element(By.CSS_SELECTOR, "input[name='otpCode'], input[name='code'], input[name='cvf_verification_code']")
                    except:
                        pass
                
                # If still not found, try by input type
                if not verif_field:
                    try:
                        verif_field = driver.find_element(By.CSS_SELECTOR, "input[type='number'], input[type='tel']")
                    except:
                        pass
                
                if not verif_field:
                    return None, "2FA required but couldn't find verification code input field"
                
                # Enter verification code
                verif_field.send_keys(verification_code)
                
                # Find submit button
                submit_button = None
                
                # Try different ways to find the submit button
                for button_id in ['auth-verify-button', 'auth-signin-button', 'cvf-submit-otp-button']:
                    try:
                        submit_button = driver.find_element(By.ID, button_id)
                        break
                    except:
                        pass
                
                if not submit_button:
                    try:
                        # Try to find by type and value
                        submit_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
                    except:
                        pass
                
                if not submit_button:
                    # Try to find by text content
                    for text in ['submit', 'verify', 'continue']:
                        try:
                            submit_button = driver.find_element(By.XPATH, f"//button[contains(text(), '{text}')]")
                            break
                        except:
                            pass
                
                if not submit_button:
                    return None, "2FA required but couldn't find submit button"
                
                # Click submit
                submit_button.click()
                time.sleep(5)  # Allow for verification
                
            except Exception as e:
                st.error(f"Error handling 2FA: {e}")
                driver.quit()
                return None, f"Error handling 2FA: {e}"
        
        elif not verification_code and ('verification' in page_source or 'two-factor' in page_source or 'otp' in page_source):
            # Need 2FA but no code provided
            st.session_state.needs_2fa = True
            driver.quit()
            return None, "2FA_REQUIRED"
        
        # Check if login was successful
        time.sleep(5)  # Allow page to fully load
        current_url = driver.current_url
        
        if "signin" in current_url or "ap/signin" in current_url:
            # Still on login page, authentication failed
            driver.quit()
            return None, "Login failed. Check your credentials."
        
        # Extract cookies
        cookies = driver.get_cookies()
        
        # Convert to format usable by requests
        cookies_dict = {cookie['name']: cookie['value'] for cookie in cookies}
        
        # Save screenshot for debugging
        driver.save_screenshot(os.path.join(temp_dir, "amazon_logged_in.png"))
        
        driver.quit()
        return cookies_dict, "Cookies extracted successfully"
        
    except Exception as e:
        st.error(f"Error extracting cookies: {e}")
        if 'driver' in locals():
            driver.quit()
        return None, f"Error extracting cookies: {e}"

# Function to create a session with the provided cookies
def create_session_with_cookies(cookies_dict):
    session = requests.Session()
    
    # Update headers to mimic a browser
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    
    # Set cookies
    for name, value in cookies_dict.items():
        session.cookies.set(name, value, domain='.amazon.com')
    
    return session

# Function to verify login status
def verify_amazon_login(session, test_url):
    try:
        response = session.get(test_url)
        
        # Check if redirected to sign-in page
        if 'signin' in response.url or 'ap/signin' in response.url:
            return False, "Not logged in. Amazon is requesting authentication."
        
        # Check for indicators of being logged in
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for account/profile elements that indicate logged-in state
        account_list = soup.find(id='nav-link-accountList') or soup.find(id='nav-tools')
        
        if account_list and ('account' in response.text.lower() or 'hello' in response.text.lower()):
            # Try to find user name
            name_element = soup.select_one('#nav-link-accountList-nav-line-1, .nav-line-1')
            username = name_element.text.strip() if name_element else "User"
            
            return True, f"Successfully authenticated as {username}!"
        
        return False, "Login verification failed. Cookies may be expired."
    
    except Exception as e:
        return False, f"Error verifying login: {e}"

# Function to fetch and process orders
def fetch_amazon_orders(session, orders_url, download_dir, max_orders=5):
    try:
        response = session.get(orders_url)
        
        if response.status_code != 200:
            return False, f"Failed to load orders page. Status code: {response.status_code}"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try different selectors for order containers
        order_containers = soup.select('.order') or soup.select('.js-order-card') or soup.select('.order-card')
        
        if not order_containers:
            return False, "Could not find any orders on the page. Amazon may have changed their page layout."
        
        orders_processed = 0
        successful_downloads = 0
        
        for i, container in enumerate(order_containers):
            if i >= max_orders:
                break
                
            try:
                # Extract order ID
                order_id_elem = container.select_one('.order-info .value, .order-id, .yo-orderid, [data-test-id="order-id-container"]')
                order_id = order_id_elem.text.strip() if order_id_elem else f"Order-{i+1}"
                
                # Clean up order ID (remove extra text)
                order_id = re.sub(r'Order #', '', order_id).strip()
                order_id = re.sub(r'\s+', '-', order_id)
                
                st.info(f"🔍 Processing order: {order_id}")
                
                # Find invoice link
                invoice_link = None
                invoice_links = []
                
                # Try different selectors and approaches
                for link in container.select('a'):
                    href = link.get('href', '')
                    text = link.text.lower()
                    
                    if ('invoice' in text or 'invoice' in href.lower() or 
                        'receipt' in text or 'receipt' in href.lower()):
                        full_url = 'https://www.amazon.com' + href if not href.startswith('http') else href
                        invoice_links.append(full_url)
                
                if not invoice_links:
                    # Try to find "Order Details" link
                    for link in container.select('a'):
                        href = link.get('href', '')
                        text = link.text.lower()
                        
                        if ('order details' in text or 'details' in text or 
                            'view order' in text or 'order-details' in href):
                            order_details_url = 'https://www.amazon.com' + href if not href.startswith('http') else href
                            
                            # Visit order details page to find invoice link
                            details_response = session.get(order_details_url)
                            details_soup = BeautifulSoup(details_response.text, 'html.parser')
                            
                            for details_link in details_soup.select('a'):
                                details_href = details_link.get('href', '')
                                details_text = details_link.text.lower()
                                
                                if ('invoice' in details_text or 'invoice' in details_href.lower() or
                                    'receipt' in details_text or 'receipt' in details_href.lower()):
                                    full_url = 'https://www.amazon.com' + details_href if not details_href.startswith('http') else details_href
                                    invoice_links.append(full_url)
                            
                            break
                
                if not invoice_links:
                    st.warning(f"⚠️ No invoice link found for order {order_id}. Skipping.")
                    continue
                
                # Visit the first invoice link
                invoice_link = invoice_links[0]
                st.info(f"📄 Found invoice link for order {order_id}")
                
                invoice_response = session.get(invoice_link)
                invoice_soup = BeautifulSoup(invoice_response.text, 'html.parser')
                
                # Look for printable order summary link
                printable_link = None
                
                # Method 1: Direct link in a popover
                popover_links = invoice_soup.select('.a-popover-content a, [data-action="a-popover"] a')
                for link in popover_links:
                    link_text = link.text.lower()
                    if 'print' in link_text or 'summary' in link_text or 'invoice' in link_text:
                        printable_link = link.get('href')
                        break
                
                # Method 2: From "Print Order Summary" button
                if not printable_link:
                    print_buttons = invoice_soup.select('input[type="submit"][value*="Print"], button:contains("Print")')
                    if print_buttons:
                        # This might be a form submission, extract form action
                        parent_form = print_buttons[0].find_parent('form')
                        if parent_form:
                            printable_link = parent_form.get('action')
                
                # Method 3: Directly from page links
                if not printable_link:
                    for link in invoice_soup.select('a'):
                        href = link.get('href', '')
                        text = link.text.lower()
                        if ('print' in text and ('summary' in text or 'invoice' in text)) or 'print-summary' in href:
                            printable_link = href
                            break
                
                if not printable_link:
                    st.warning(f"⚠️ No printable summary link found for order {order_id}. Skipping.")
                    continue
                
                # Make printable link absolute
                printable_link = 'https://www.amazon.com' + printable_link if not printable_link.startswith('http') else printable_link
                
                # Download the printable order summary
                st.info(f"📥 Downloading invoice for order {order_id}")
                
                summary_response = session.get(printable_link)
                
                # Check if it's a PDF or HTML
                content_type = summary_response.headers.get('Content-Type', '').lower()
                
                filename = f"Amazon_Invoice_{order_id}.pdf"
                filepath = os.path.join(download_dir, filename)
                
                if 'pdf' in content_type:
                    # Direct PDF download
                    with open(filepath, 'wb') as f:
                        f.write(summary_response.content)
                else:
                    # It's HTML that should be printed to PDF
                    # Save the HTML temporarily
                    html_path = os.path.join(temp_dir, f"order_{order_id}.html")
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(summary_response.text)
                    
                    # Let the user know they need to print it manually
                    st.info(f"📄 Saved HTML for order {order_id}. You'll need to open and print it to PDF manually.")
                    
                    # Provide the HTML content for download
                    with open(html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                        
                    st.download_button(
                        label=f"Download HTML for Order {order_id}",
                        data=html_content,
                        file_name=f"Amazon_Order_{order_id}.html",
                        mime="text/html"
                    )
                    
                    continue
                
                st.success(f"✅ Successfully downloaded invoice for order {order_id}")
                successful_downloads += 1
                
            except Exception as e:
                st.error(f"❌ Error processing order {i+1}: {str(e)}")
            
            orders_processed += 1
        
        return True, f"Processed {orders_processed} orders with {successful_downloads} successful downloads."
    
    except Exception as e:
        return False, f"Error fetching orders: {str(e)}"

# Main action button
if st.button("Login & Download Invoices"):
    if not email or not password:
        st.error("❌ Please enter your Amazon email and password.")
    elif 'needs_2fa' in st.session_state and st.session_state.needs_2fa and not 'verification_code' in locals():
        st.error("❌ Please enter the verification code sent to your device.")
    else:
        # Reset 2FA flag if already set
        verification_code_val = verification_code if 'verification_code' in locals() else None
        
        # Extract cookies
        with st.spinner("🔄 Logging in to Amazon and extracting cookies..."):
            cookies_dict, message = extract_amazon_cookies(email, password, verification_code_val)
            
            if message == "2FA_REQUIRED":
                st.warning("Amazon requires two-factor authentication. Please enter the verification code sent to your device.")
                st.rerun()  # Rerun to show verification code input
            elif not cookies_dict:
                st.error(f"Failed to extract cookies: {message}")
            else:
                st.success("✅ Successfully extracted Amazon cookies!")
                
                # Verify login
                with st.spinner("🔄 Verifying login status..."):
                    session = create_session_with_cookies(cookies_dict)
                    logged_in, login_message = verify_amazon_login(session, orders_url)
                    
                    if logged_in:
                        st.success(login_message)
                        
                        # Fetch and download invoices
                        with st.spinner("🔄 Fetching orders and downloading invoices..."):
                            success, result_message = fetch_amazon_orders(session, orders_url, download_dir)
                            
                            if success:
                                st.success(result_message)
                                st.balloons()
                            else:
                                st.error(result_message)
                    else:
                        st.error(login_message)

# Add disclaimer
st.sidebar.markdown("---")
st.sidebar.info("""
**Disclaimer:** This app uses your Amazon credentials to log in and extract your cookie data. 
Your credentials are used only in this session and are not stored. Please use responsibly and in accordance 
with Amazon's Terms of Service.
""")

st.sidebar.markdown("---")
st.sidebar.subheader("❓ Troubleshooting")
st.sidebar.markdown("""
- If you're required to enter a verification code, enter it when prompted
- If downloads fail, try refreshing the page and starting again
- Make sure you're using the correct Amazon domain for your region
- Check your download directory to make sure it's accessible
""")
