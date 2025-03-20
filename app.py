import time
import os
import streamlit as st
import requests
from bs4 import BeautifulSoup
import tempfile
import json
from datetime import datetime
import re
import urllib.parse

st.set_page_config(page_title="Amazon Invoice Downloader", page_icon="📦")

st.title("📦 Amazon Order Information Extractor")
st.write("This app logs into Amazon and extracts your order information without using browser automation.")

# Create a temporary directory as fallback
temp_dir = tempfile.mkdtemp()
st.sidebar.info(f"Temporary data directory: {temp_dir}")

# Initialize session state to store cookies and data
if 'session_cookies' not in st.session_state:
    st.session_state.session_cookies = {}
if 'orders_data' not in st.session_state:
    st.session_state.orders_data = []
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# User inputs
with st.form("login_form"):
    st.subheader("Amazon Login")
    email = st.text_input("📧 Enter your Amazon email:", type="default")
    password = st.text_input("🔑 Enter your Amazon password:", type="password")
    orders_url = st.text_input("🔗 Enter Amazon orders list URL:", 
                              value="https://www.amazon.com/gp/css/order-history")
    download_dir = st.text_input("📁 Enter directory to save order data:", 
                                value=os.path.join(os.path.expanduser("~"), "amazon_orders"))
    
    submit_button = st.form_submit_button("Login to Amazon")

# Ensure download directory exists
if download_dir and not os.path.exists(download_dir):
    try:
        os.makedirs(download_dir, exist_ok=True)
        st.success(f"Created download directory: {download_dir}")
    except Exception as e:
        st.error(f"Failed to create download directory: {e}")
        download_dir = temp_dir
        st.info(f"Using temporary directory instead: {download_dir}")

# Create a session with proper headers
def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    return session

# Login to Amazon
def login_to_amazon(session, email, password):
    # Get the sign-in page first
    try:
        signin_url = "https://www.amazon.com/ap/signin"
        params = {
            'openid.pape.max_auth_age': '0',
            'openid.return_to': 'https://www.amazon.com/?ref_=nav_signin',
            'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
            'openid.assoc_handle': 'usflex',
            'openid.mode': 'checkid_setup',
            'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
            'openid.ns': 'http://specs.openid.net/auth/2.0',
        }
        
        response = session.get(signin_url, params=params)
        
        # For debugging - save HTML to examine the form structure
        with open(os.path.join(temp_dir, "amazon_login_page.html"), "w", encoding="utf-8") as f:
            f.write(response.text)
        
        # Extract form data
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try multiple form selectors
        form = None
        for form_id in ['signIn', 'ap_signin_form', 'ap-signin-form']:
            form = soup.find('form', {'name': form_id}) or soup.find('form', {'id': form_id})
            if form:
                break
                
        # If still not found, try to find any form with password field
        if not form:
            forms = soup.find_all('form')
            for f in forms:
                if f.find('input', {'type': 'password'}) or f.find('input', {'name': 'password'}):
                    form = f
                    break
        
        # If still not found, try to find any form with email field        
        if not form:
            forms = soup.find_all('form')
            for f in forms:
                if f.find('input', {'type': 'email'}) or f.find('input', {'name': 'email'}):
                    form = f
                    break
        
        if not form:
            # Last resort - just find any form
            forms = soup.find_all('form')
            if forms:
                form = forms[0]
            else:
                return False, "Couldn't find any form on the login page. Amazon may have significantly changed their login process."
        
        # Get hidden form inputs
        form_data = {}
        for input_tag in form.find_all('input'):
            name = input_tag.get('name')
            value = input_tag.get('value', '')
            if name:
                form_data[name] = value
                
        # Find the email input field
        email_field_name = None
        for input_tag in form.find_all('input'):
            input_type = input_tag.get('type', '')
            input_name = input_tag.get('name', '')
            input_id = input_tag.get('id', '')
            
            if input_type == 'email' or 'email' in input_name.lower() or 'email' in input_id.lower():
                email_field_name = input_name
                break
        
        # If not found, try some common field names
        if not email_field_name:
            for field_name in ['email', 'ap_email', 'username', 'login']:
                if field_name in form_data:
                    email_field_name = field_name
                    break
        
        # Add email
        if email_field_name:
            form_data[email_field_name] = email
        else:
            # If we can't find email field, add email to common field names
            for field_name in ['email', 'ap_email', 'username', 'login']:
                form_data[field_name] = email
        
        # Submit email form
        post_url = form.get('action')
        if not post_url:
            post_url = signin_url
        elif not post_url.startswith('http'):
            post_url = 'https://www.amazon.com' + post_url
            
        response = session.post(post_url, data=form_data)
        
        # For debugging - save HTML to examine the password form structure
        with open(os.path.join(temp_dir, "amazon_password_page.html"), "w", encoding="utf-8") as f:
            f.write(response.text)
        
        # Now handle password page
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try multiple form selectors for password page
        form = None
        for form_id in ['signIn', 'ap_signin_form', 'ap-signin-form']:
            form = soup.find('form', {'name': form_id}) or soup.find('form', {'id': form_id})
            if form:
                break
                
        # If still not found, try to find any form with password field
        if not form:
            forms = soup.find_all('form')
            for f in forms:
                if f.find('input', {'type': 'password'}) or f.find('input', {'name': 'password'}):
                    form = f
                    break
        
        if not form:
            return False, "Couldn't find the password form. Amazon may have changed their page layout. Check the debug files in the temp directory."
        
        # Get hidden form inputs for password page
        form_data = {}
        for input_tag in form.find_all('input'):
            name = input_tag.get('name')
            value = input_tag.get('value', '')
            if name:
                form_data[name] = value
                
        # Find the password input field
        password_field_name = None
        for input_tag in form.find_all('input'):
            input_type = input_tag.get('type', '')
            input_name = input_tag.get('name', '')
            
            if input_type == 'password' or 'password' in input_name.lower():
                password_field_name = input_name
                break
        
        # If not found, try some common field names
        if not password_field_name:
            for field_name in ['password', 'ap_password']:
                if field_name in form_data:
                    password_field_name = field_name
                    break
        
        # Add password
        if password_field_name:
            form_data[password_field_name] = password
        else:
            # If we can't find password field, add password to common field names
            for field_name in ['password', 'ap_password']:
                form_data[field_name] = password
        
        # Submit password form
        post_url = form.get('action')
        if not post_url:
            post_url = signin_url
        elif not post_url.startswith('http'):
            post_url = 'https://www.amazon.com' + post_url
            
        response = session.post(post_url, data=form_data)
        
        # Save final response for debugging
        with open(os.path.join(temp_dir, "amazon_post_login.html"), "w", encoding="utf-8") as f:
            f.write(response.text)
        
        # Check if login was successful
        if 'auth-error-message' in response.text or 'signIn' in response.url:
            return False, "Login failed. Please check your credentials."
        
        # Check for OTP/verification
        if 'cvf-page-content' in response.text or 'auth-mfa-form' in response.text:
            # Return special status for 2FA
            return "2FA_REQUIRED", response
        
        return True, "Login successful"
        
    except Exception as e:
        return False, f"Error during login: {str(e)}"

# Parse order details from orders page
def parse_orders(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    orders = []
    
    # Find all order containers
    order_containers = soup.select('.order')
    
    if not order_containers:
        # Try alternative selectors if the first one doesn't work
        order_containers = soup.select('.js-order-card')
    
    if not order_containers:
        return [], "Could not find any orders on the page. Amazon may have changed their page layout."
    
    for container in order_containers[:10]:  # Limit to first 10 orders
        try:
            # Extract order ID
            order_id_elem = container.select_one('.order-info .value, .order-id')
            order_id = order_id_elem.text.strip() if order_id_elem else "Unknown"
            
            # Extract order date
            order_date_elem = container.select_one('.order-info .order-date, .date-container')
            order_date = order_date_elem.text.strip() if order_date_elem else "Unknown"
            
            # Extract total
            total_elem = container.select_one('.a-column .value, .yohtmlc-order-total')
            total = total_elem.text.strip() if total_elem else "Unknown"
            
            # Extract items
            items = []
            item_elements = container.select('.a-fixed-left-grid-inner, .a-row.yohtmlc-item')
            for item_elem in item_elements:
                item_name_elem = item_elem.select_one('.a-col-right .a-text-bold, .a-link-normal')
                item_name = item_name_elem.text.strip() if item_name_elem else "Unknown Item"
                items.append(item_name)
            
            # Extract links
            invoice_link = None
            details_link = None
            
            links = container.select('a')
            for link in links:
                href = link.get('href', '')
                text = link.text.strip().lower()
                
                if 'order-details' in href or '/gp/your-account/order-details' in href:
                    details_link = 'https://www.amazon.com' + href if not href.startswith('http') else href
                
                if 'invoice' in text or 'invoice' in href:
                    invoice_link = 'https://www.amazon.com' + href if not href.startswith('http') else href
            
            orders.append({
                'order_id': order_id,
                'order_date': order_date,
                'total': total,
                'items': items,
                'invoice_link': invoice_link,
                'details_link': details_link
            })
            
        except Exception as e:
            st.warning(f"Error parsing an order: {str(e)}")
            continue
    
    return orders, "Successfully parsed orders"

# Handle 2FA verification
def handle_2fa(session, response, otp_code):
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the form
        form = soup.find('form', {'id': 'auth-mfa-form'}) or soup.find('form', {'name': 'cvf-form'})
        
        if not form:
            return False, "Could not find the 2FA form."
        
        # Get all form inputs
        form_data = {}
        for input_tag in form.find_all('input'):
            name = input_tag.get('name')
            value = input_tag.get('value')
            if name and value:
                form_data[name] = value
        
        # Add the OTP code
        form_data['otpCode'] = otp_code
        # The field might be named differently
        if 'code' in form_data:
            form_data['code'] = otp_code
        if 'cvf_verification_code' in form_data:
            form_data['cvf_verification_code'] = otp_code
        
        # Get the form action URL
        post_url = form.get('action')
        if not post_url.startswith('http'):
            post_url = 'https://www.amazon.com' + post_url
        
        # Submit the form
        response = session.post(post_url, data=form_data)
        
        # Check if login was successful
        if 'auth-error-message' in response.text or 'cvf-page-content' in response.text or 'auth-mfa-form' in response.text:
            return False, "2FA verification failed. Please check your code."
        
        return True, "Login successful!"
        
    except Exception as e:
        return False, f"Error during 2FA verification: {str(e)}"

# Main function to handle button click
if submit_button:
    if not email or not password:
        st.error("❌ Please enter your Amazon email and password!")
    else:
        with st.spinner("🔄 Logging into Amazon..."):
            # Create a new session
            session = create_session()
            
            # Try to login
            result, response_or_message = login_to_amazon(session, email, password)
            
            if result == True:
                st.success(response_or_message)
                st.session_state.session_cookies = dict(session.cookies)
                st.session_state.logged_in = True
            elif result == "2FA_REQUIRED":
                st.warning("Amazon requires additional verification (OTP/2FA).")
                st.session_state.pending_2fa = True
                st.session_state.temp_session = session
                st.session_state.temp_response = response_or_message
            else:
                st.error(response_or_message)

# Handle 2FA verification if needed
if 'pending_2fa' in st.session_state and st.session_state.pending_2fa:
    st.subheader("📱 Two-Factor Authentication Required")
    st.write("Please enter the verification code sent to your phone or email.")
    
    otp_code = st.text_input("Enter verification code:", key="otp_input")
    
    if st.button("Submit Verification Code"):
        if not otp_code:
            st.error("Please enter the verification code.")
        else:
            with st.spinner("Verifying..."):
                session = st.session_state.temp_session
                response = st.session_state.temp_response
                
                success, message = handle_2fa(session, response, otp_code)
                
                if success:
                    st.success(message)
                    st.session_state.session_cookies = dict(session.cookies)
                    st.session_state.logged_in = True
                    st.session_state.pending_2fa = False
                    # Force a rerun to update the UI
                    st.rerun()
                else:
                    st.error(message)

# Button to fetch orders if logged in
if st.session_state.logged_in:
    if st.button("Fetch Order History"):
        with st.spinner("🔄 Retrieving order history..."):
            try:
                # Recreate session with saved cookies
                session = create_session()
                session.cookies.update(st.session_state.session_cookies)
                
                # Fetch orders page
                response = session.get(orders_url)
                
                if response.status_code == 200:
                    orders, message = parse_orders(response.text)
                    
                    if orders:
                        st.session_state.orders_data = orders
                        st.success(f"✅ Successfully retrieved {len(orders)} orders!")
                        
                        # Save to JSON file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = os.path.join(download_dir, f"amazon_orders_{timestamp}.json")
                        
                        with open(filename, 'w') as f:
                            json.dump(orders, f, indent=2)
                            
                        st.success(f"📄 Saved orders data to: {filename}")
                    else:
                        st.warning(message)
                else:
                    st.error(f"❌ Failed to fetch orders page. Status code: {response.status_code}")
                    
            except Exception as e:
                st.error(f"❌ Error retrieving orders: {str(e)}")

# Display orders if available
if st.session_state.orders_data:
    st.subheader("📋 Your Orders")
    
    for i, order in enumerate(st.session_state.orders_data):
        with st.expander(f"Order #{i+1}: {order['order_id']} - {order['order_date']} - {order['total']}"):
            st.write("**Items:**")
            for item in order['items']:
                st.write(f"- {item}")
                
            if order['details_link']:
                st.markdown(f"[View Order Details]({order['details_link']})")
                
            if order['invoice_link']:
                st.markdown(f"[View Invoice]({order['invoice_link']})")
                
    # Export options
    st.subheader("📤 Export Options")
    
    if st.button("Export as CSV"):
        try:
            import csv
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(download_dir, f"amazon_orders_{timestamp}.csv")
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Write header
                writer.writerow(['Order ID', 'Date', 'Total', 'Items', 'Details Link', 'Invoice Link'])
                
                # Write data
                for order in st.session_state.orders_data:
                    writer.writerow([
                        order['order_id'],
                        order['order_date'],
                        order['total'],
                        '; '.join(order['items']),
                        order['details_link'] or '',
                        order['invoice_link'] or ''
                    ])
                    
            st.success(f"✅ CSV file saved to: {filename}")
            
            # Provide download link
            with open(filename, 'r', encoding='utf-8') as f:
                csv_data = f.read()
                
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"amazon_orders_{timestamp}.csv",
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"❌ Error exporting to CSV: {str(e)}")
    
# Add disclaimer
st.sidebar.markdown("---")
st.sidebar.info("""
**Disclaimer:** This app uses your Amazon credentials to log in and extract data. 
Your credentials are not stored beyond this session. Please use responsibly and in accordance 
with Amazon's Terms of Service.
""")

# Add help information
st.sidebar.markdown("---")
st.sidebar.subheader("❓ Help")
st.sidebar.markdown("""
1. Enter your Amazon email and password
2. Click "Login to Amazon"
3. Once logged in, click "Fetch Order History"
4. View your orders and export as needed

**Note:** This app does not support Amazon accounts that require Two-Factor Authentication (2FA) or OTP verification.
""")
