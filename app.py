import time
import os
import streamlit as st
import requests
from bs4 import BeautifulSoup
import tempfile

st.title("📦 Amazon Invoice & Order Summary Downloader")
st.write("This app logs into Amazon, downloads invoice PDFs, and saves them to your selected directory.")

# User inputs
email = st.text_input("📧 Enter your Amazon email:", type="default")
password = st.text_input("🔑 Enter your Amazon password:", type="password")
orders_url = st.text_input("🔗 Enter Amazon orders list URL:")
download_dir = st.text_input("📁 Enter directory to save invoices:", value=r"/app/invoices")

# Ensure download directory exists
if not os.path.exists(download_dir):
    try:
        os.makedirs(download_dir, exist_ok=True)
        st.success(f"Created download directory: {download_dir}")
    except Exception as e:
        st.error(f"Failed to create download directory: {e}")
        # Create a temp directory as fallback
        download_dir = tempfile.mkdtemp()
        st.info(f"Using temporary directory instead: {download_dir}")

if st.button("Start Downloading Invoices"):
    if not email or not password or not orders_url or not download_dir:
        st.error("❌ Please fill all fields!")
    else:
        st.info("🚀 Starting invoice download process...")

        # Create a session with proper headers
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        try:
            # Navigate to Amazon Orders Page
            st.info("🔄 Navigating to Amazon Orders Page...")
            response = session.get(orders_url)

            # Login if required
            if "signin" in response.url:
                st.warning("🔒 Amazon login required. Logging in...")
                
                # Extract form data for email
                soup = BeautifulSoup(response.text, 'html.parser')
                form = soup.find('form', {'name': 'signIn'})
                
                if not form:
                    st.error("❌ Could not find the login form. Amazon may have changed their layout.")
                    st.stop()
                
                form_data = {}
                for input_tag in form.find_all('input'):
                    name = input_tag.get('name')
                    value = input_tag.get('value', '')
                    if name:
                        form_data[name] = value
                
                # Add email
                form_data['email'] = email
                
                # Submit email form
                post_url = form.get('action')
                if not post_url.startswith('http'):
                    post_url = 'https://www.amazon.com' + post_url
                
                response = session.post(post_url, data=form_data)
                
                # Handle password page
                soup = BeautifulSoup(response.text, 'html.parser')
                form = soup.find('form', {'name': 'signIn'})
                
                if not form:
                    st.error("❌ Could not find the password form. Amazon may have changed their layout.")
                    st.stop()
                
                form_data = {}
                for input_tag in form.find_all('input'):
                    name = input_tag.get('name')
                    value = input_tag.get('value', '')
                    if name:
                        form_data[name] = value
                
                # Add password
                form_data['password'] = password
                
                # Submit password form
                post_url = form.get('action')
                if not post_url.startswith('http'):
                    post_url = 'https://www.amazon.com' + post_url
                
                response = session.post(post_url, data=form_data)
                
                # Check if login was successful
                if 'auth-error-message' in response.text or 'signin' in response.url:
                    st.error("❌ Login failed. Please check your credentials.")
                    st.stop()
                
                # Check for 2FA/OTP verification
                if 'cvf-page-content' in response.text or 'auth-mfa-form' in response.text:
                    # Display 2FA input form
                    st.warning("Amazon requires additional verification (OTP/2FA).")
                    verification_code = st.text_input("Enter the verification code sent to your device:")
                    
                    if st.button("Submit Verification Code"):
                        if not verification_code:
                            st.error("Please enter the verification code.")
                        else:
                            try:
                                # Find the 2FA form
                                soup = BeautifulSoup(response.text, 'html.parser')
                                form = soup.find('form', {'id': 'auth-mfa-form'}) or soup.find('form', {'name': 'cvf-form'})
                                
                                if not form:
                                    st.error("Could not find the verification form.")
                                    st.stop()
                                
                                # Get form data
                                form_data = {}
                                for input_tag in form.find_all('input'):
                                    name = input_tag.get('name')
                                    value = input_tag.get('value', '')
                                    if name:
                                        form_data[name] = value
                                
                                # Add verification code
                                # Try different possible field names
                                form_data['otpCode'] = verification_code
                                form_data['code'] = verification_code
                                form_data['cvf_verification_code'] = verification_code
                                
                                # Submit form
                                post_url = form.get('action')
                                if not post_url.startswith('http'):
                                    post_url = 'https://www.amazon.com' + post_url
                                
                                response = session.post(post_url, data=form_data)
                                
                                # Check if verification was successful
                                if 'auth-error-message' in response.text or 'cvf-page-content' in response.text or 'auth-mfa-form' in response.text:
                                    st.error("Verification failed. Please check your code.")
                                    st.stop()
                                
                                st.success("✅ Verification successful!")
                            except Exception as e:
                                st.error(f"Error during verification: {e}")
                                st.stop()
                    else:
                        st.stop()
                
                st.success("✅ Successfully logged in!")
            
            # Navigate to orders page if not already there
            if "/order-history" not in response.url:
                response = session.get(orders_url)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if we're on the orders page
            if not soup.select('.order') and not soup.select('.js-order-card'):
                st.error("❌ Could not load orders list. Please check if you're logged in properly.")
                st.stop()
            
            st.info("✅ Orders list loaded successfully.")
            
            # Process each order
            order_containers = soup.select('.order') or soup.select('.js-order-card')
            
            for i, container in enumerate(order_containers[:5]):  # Process top 5 orders
                try:
                    # Extract order ID
                    order_id_elem = container.select_one('.order-info .value, .order-id')
                    order_id = order_id_elem.text.strip() if order_id_elem else f"Order {i+1}"
                    
                    st.info(f"🆔 Processing Order {i+1}: {order_id}")
                    
                    # Find invoice link
                    invoice_link = None
                    for link in container.select('a'):
                        if 'invoice' in link.text.lower() or 'invoice' in link.get('href', '').lower():
                            href = link.get('href')
                            invoice_link = 'https://www.amazon.com' + href if not href.startswith('http') else href
                            break
                    
                    if not invoice_link:
                        st.warning(f"⚠ No invoice link found for Order {order_id}. Skipping.")
                        continue
                    
                    # Follow invoice link
                    st.info(f"📄 Accessing invoice for Order {order_id}")
                    response = session.get(invoice_link)
                    
                    # Find printable order summary link
                    soup = BeautifulSoup(response.text, 'html.parser')
                    printable_link = None
                    
                    # Try different selectors for printable summary link
                    selectors = [
                        "a:contains('Printable Order Summary')",
                        "a[href*='print-summary']",
                        ".a-popover-content a"
                    ]
                    
                    for selector in selectors:
                        try:
                            if selector.startswith("a:contains"):
                                # Handle BeautifulSoup's lack of :contains selector
                                link_text = selector.split("'")[1]
                                for link in soup.find_all('a'):
                                    if link_text in link.text:
                                        printable_link = link.get('href')
                                        break
                            else:
                                link_elem = soup.select_one(selector)
                                if link_elem:
                                    printable_link = link_elem.get('href')
                            
                            if printable_link:
                                break
                        except Exception:
                            continue
                    
                    if not printable_link:
                        st.warning(f"⚠ Could not find printable order summary link for Order {order_id}. Skipping.")
                        continue
                    
                    # Make sure the URL is absolute
                    if not printable_link.startswith('http'):
                        printable_link = 'https://www.amazon.com' + printable_link
                    
                    # Download the printable order summary
                    st.info(f"📑 Downloading Printable Order Summary for Order {order_id}")
                    response = session.get(printable_link)
                    
                    # Save the PDF
                    filename = f"Order_{order_id}_Summary.pdf"
                    filepath = os.path.join(download_dir, filename)
                    
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    st.success(f"✅ Invoice Downloaded for Order {order_id} to {filepath}!")
                
                except Exception as e:
                    st.error(f"❌ Error processing Order {i+1}: {e}")
            
            st.success("✅ Process Completed!")
            
        except Exception as e:
            st.error(f"❌ An error occurred: {e}")
