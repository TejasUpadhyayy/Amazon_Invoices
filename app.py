import time
import os
import streamlit as st
import requests
from bs4 import BeautifulSoup
import tempfile
import json
import re

st.set_page_config(page_title="Amazon Invoice Downloader", page_icon="📦")

st.title("📦 Amazon Invoice Downloader (Cookie-Based)")
st.write("This app uses your Amazon cookies to download invoice PDFs without requiring login.")

# Create a temporary directory as fallback
temp_dir = tempfile.mkdtemp()
st.sidebar.info(f"Temporary directory: {temp_dir}")

# User inputs
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

# Cookie input section
with st.expander("🍪 Amazon Cookie Setup", expanded=True):
    st.markdown("""
    ### How to get your Amazon cookies:
    
    1. Log in to Amazon in your browser
    2. Open Developer Tools (F12 or right-click → Inspect)
    3. Go to the "Application" or "Storage" tab
    4. Click on "Cookies" and select the Amazon domain
    5. Look for the following cookies and copy their values:
        - `session-id`
        - `session-token`
        - `ubid-main` or `ubid-acbus` (depending on your region)
        - `at-main` (authentication token)
    """)
    
    # Cookie inputs
    session_id = st.text_input("session-id:", type="password")
    session_token = st.text_input("session-token:", type="password")
    ubid = st.text_input("ubid-main or ubid-acbus:", type="password")
    at_main = st.text_input("at-main:", type="password")
    
    # Option to paste raw cookie string
    st.markdown("---")
    st.write("OR paste your entire cookie string:")
    raw_cookies = st.text_area("Raw Cookie String (from browser):", height=100, help="Copy the entire cookie string from your browser")
    
    # Parse raw cookies if provided
    if raw_cookies:
        try:
            # Extract individual cookies from raw string
            cookie_pattern = r'([^=]+)=([^;]+)'
            extracted_cookies = re.findall(cookie_pattern, raw_cookies)
            
            cookie_dict = {name.strip(): value.strip() for name, value in extracted_cookies}
            
            # Auto-fill individual fields if they're empty
            if not session_id and 'session-id' in cookie_dict:
                session_id = cookie_dict['session-id']
            if not session_token and 'session-token' in cookie_dict:
                session_token = cookie_dict['session-token']
            if not ubid:
                if 'ubid-main' in cookie_dict:
                    ubid = cookie_dict['ubid-main']
                elif 'ubid-acbus' in cookie_dict:
                    ubid = cookie_dict['ubid-acbus']
            if not at_main and 'at-main' in cookie_dict:
                at_main = cookie_dict['at-main']
                
            st.success("✅ Cookies extracted successfully!")
        except Exception as e:
            st.error(f"Error parsing cookie string: {e}")

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
        if value:  # Only set non-empty cookies
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
if st.button("Download Invoices"):
    if not download_dir:
        st.error("❌ Please specify a download directory.")
    elif not (session_id or raw_cookies):
        st.error("❌ Please provide either individual cookies or a raw cookie string.")
    else:
        # Prepare cookies
        cookies = {
            'session-id': session_id,
            'session-token': session_token,
            'ubid-main': ubid if 'main' in ubid or not ubid else '',
            'ubid-acbus': ubid if 'acbus' in ubid or not ubid else '',
            'at-main': at_main
        }
        
        # Add all cookies from raw string if provided
        if raw_cookies:
            cookie_pattern = r'([^=]+)=([^;]+)'
            extracted_cookies = re.findall(cookie_pattern, raw_cookies)
            for name, value in extracted_cookies:
                cookies[name.strip()] = value.strip()
        
        # Create session with cookies
        session = create_session_with_cookies(cookies)
        
        # Verify login status
        with st.spinner("🔄 Verifying login status..."):
            logged_in, message = verify_amazon_login(session, orders_url)
            
            if logged_in:
                st.success(message)
                
                # Fetch and process orders
                with st.spinner("🔄 Fetching orders and downloading invoices..."):
                    success, result_message = fetch_amazon_orders(session, orders_url, download_dir)
                    
                    if success:
                        st.success(result_message)
                        st.balloons()
                    else:
                        st.error(result_message)
            else:
                st.error(message)
                st.info("Please check your cookies and try again. You may need to re-login to Amazon and get fresh cookies.")

# Add help and instructions
st.sidebar.markdown("---")
st.sidebar.subheader("📋 Instructions")
st.sidebar.markdown("""
### Getting and Using Cookies

**Option 1: Chrome Browser**
1. Login to Amazon
2. Press F12 or right-click and select "Inspect"
3. Go to Application tab > Cookies > amazon.com
4. Find the required cookies and copy their values

**Option 2: Firefox Browser**
1. Login to Amazon
2. Press F12 or right-click and select "Inspect"
3. Go to Storage tab > Cookies > amazon.com
4. Find the required cookies and copy their values

**Option 3: Using a Browser Extension**
1. Install a cookie manager extension (like "EditThisCookie" for Chrome)
2. Login to Amazon
3. Click the extension icon
4. Copy all cookies or export as JSON/text

**Troubleshooting**
- If downloads fail, your cookies may be expired
- Try logging out of Amazon, logging back in, and copying fresh cookies
- Make sure you're copying cookies from the correct Amazon domain
""")

# Add disclaimer
st.sidebar.markdown("---")
st.sidebar.info("""
**Disclaimer:** This app uses your Amazon cookies to access your account data. 
Your cookies are not stored beyond this session. Please use responsibly and in accordance 
with Amazon's Terms of Service.
""")
