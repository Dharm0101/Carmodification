import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import uuid
import os
import json
from io import BytesIO
import base64

# Constants
GST_RATE = 0.18
DB_NAME = "car_mod.db"

# Initialize session state
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'selected_mods' not in st.session_state:
    st.session_state.selected_mods = []
if 'selected_color' not in st.session_state:
    st.session_state.selected_color = None
if 'selected_car' not in st.session_state:
    st.session_state.selected_car = None
if 'build_complete' not in st.session_state:
    st.session_state.build_complete = False

# Database connection helper
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# Create necessary directories
os.makedirs("bills", exist_ok=True)
os.makedirs("exports", exist_ok=True)

# Utility functions
def valid_email(email):
    import re
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email))

def valid_phone(phone):
    import re
    return bool(re.match(r"^\+?[0-9\s\-]{10,15}$", phone))

def safe_text(text):
    import re
    return re.sub(r"[^A-Za-z0-9]", "_", text)

def calculate_totals(mods, color, customer_email=None):
    """Calculate subtotal, discounts, GST, and total"""
    subtotal = 0
    
    # Calculate subtotal from modifications
    for mod in mods:
        subtotal += mod['price']
    
    if color:
        subtotal += color['price']
    
    # Apply discounts
    discount_percent = 0
    discount_amount = 0
    
    if len(mods) >= 3:
        discount_percent += 10
    
    if customer_email:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT total_visits FROM customers WHERE email = ?", (customer_email,))
        customer = cursor.fetchone()
        conn.close()
        
        if customer and customer['total_visits'] > 1:
            discount_percent += 5
    
    if discount_percent > 0:
        discount_amount = subtotal * (discount_percent / 100)
        subtotal -= discount_amount
    
    # Calculate GST
    gst = subtotal * GST_RATE
    total = subtotal + gst
    
    return {
        'subtotal': subtotal + discount_amount,  # Original subtotal
        'discount_percent': discount_percent,
        'discount_amount': discount_amount,
        'subtotal_after_discount': subtotal,
        'gst': gst,
        'total': total
    }

# Page configuration
st.set_page_config(
    page_title="Car Modification Studio",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .mod-card {
        border: 2px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        transition: all 0.3s;
    }
    .mod-card:hover {
        border-color: #667eea;
        box-shadow: 0 4px 8px rgba(102, 126, 234, 0.1);
    }
    .mod-card.selected {
        border-color: #667eea;
        background-color: rgba(102, 126, 234, 0.05);
    }
    .price-tag {
        font-weight: bold;
        color: #764ba2;
        font-size: 1.2em;
    }
    .stButton button {
        width: 100%;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Header
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown("""
    <div class="main-header">
        <h1>🚗 Custom Car Modification Studio</h1>
        <p>Transform your vehicle with premium modifications</p>
    </div>
    """, unsafe_allow_html=True)

# Sidebar - User Info & Navigation
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/car.png", width=100)
    
    if st.session_state.user_email:
        st.success(f"Welcome, {st.session_state.user_name}!")
        st.write(f"Email: {st.session_state.user_email}")
        
        # Get customer stats
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT total_visits, total_spent, loyalty_points 
            FROM customers WHERE email = ?
        """, (st.session_state.user_email,))
        stats = cursor.fetchone()
        conn.close()
        
        if stats:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Visits", stats['total_visits'])
                st.metric("Loyalty Points", stats['loyalty_points'])
            with col2:
                st.metric("Total Spent", f"₹{stats['total_spent']:.2f}")
        
        if st.button("🚪 Logout"):
            st.session_state.user_email = None
            st.session_state.user_name = None
            st.session_state.selected_mods = []
            st.session_state.selected_color = None
            st.session_state.selected_car = None
            st.rerun()
    else:
        st.info("Please login or register to access all features")
    
    st.markdown("---")
    
    # Navigation
    st.subheader("Navigation")
    pages = [
        ("🏠 Home", "home"),
        ("🔧 New Build", "build"),
        ("💰 Pricing", "pricing"),
        ("👤 Profile", "profile"),
        ("📅 Appointments", "appointments"),
        ("📊 Reports", "reports"),
        ("📤 Export Data", "export")
    ]
    
    if not st.session_state.user_email:
        pages = [("🏠 Home", "home"), ("💰 Pricing", "pricing"), ("🔐 Login/Register", "auth")]
    
    selected_page = st.radio("Go to:", [page[0] for page in pages])
    
    # Map page names to functions
    page_dict = {page[0]: page[1] for page in pages}
    current_page = page_dict[selected_page]

# Authentication Page
def auth_page():
    st.title("🔐 Authentication")
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Customer Login")
        
        with st.form("login_form"):
            email = st.text_input("Email")
            submit = st.form_submit_button("Login")
            
            if submit:
                if not valid_email(email):
                    st.error("Please enter a valid email address")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM customers WHERE email = ?", (email,))
                    customer = cursor.fetchone()
                    conn.close()
                    
                    if customer:
                        st.session_state.user_email = email
                        st.session_state.user_name = customer['name']
                        st.success(f"Welcome back, {customer['name']}!")
                        st.rerun()
                    else:
                        st.error("Customer not found. Please register first.")
    
    with tab2:
        st.subheader("New Customer Registration")
        
        with st.form("register_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Full Name")
                email = st.text_input("Email")
                phone = st.text_input("Phone Number")
            with col2:
                address = st.text_area("Address")
                city = st.text_input("City")
                state = st.text_input("State")
                pincode = st.text_input("Pincode")
            
            submit = st.form_submit_button("Register")
            
            if submit:
                if not all([name, email]):
                    st.error("Name and Email are required")
                elif not valid_email(email):
                    st.error("Please enter a valid email address")
                elif phone and not valid_phone(phone):
                    st.error("Please enter a valid phone number")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    try:
                        cursor.execute("""
                            INSERT INTO customers (email, name, phone, address, city, state, pincode) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (email, name, phone, address, city, state, pincode))
                        conn.commit()
                        
                        st.session_state.user_email = email
                        st.session_state.user_name = name
                        st.success("Registration successful! Welcome to our studio!")
                        conn.close()
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Email already registered. Please login instead.")
                        conn.close()

# Home Page
def home_page():
    st.title("🏠 Welcome to Car Modification Studio")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Why Choose Us?
        
        🎯 **Expert Craftsmanship**  
        Our technicians have 10+ years of experience in car modifications
        
        ⭐ **Premium Quality**  
        We use only certified parts and materials
        
        🔧 **Comprehensive Services**  
        From performance upgrades to aesthetic enhancements
        
        💰 **Best Prices**  
        Competitive pricing with transparent costs
        
        🛡️ **Warranty**  
        All modifications come with warranty coverage
        """)
        
        if not st.session_state.user_email:
            st.info("👉 **Login or Register** to start your modification journey!")
            if st.button("Get Started", type="primary"):
                st.session_state.current_page = "auth"
                st.rerun()
    
    with col2:
        st.markdown("""
        ### Special Offers
        
        🎁 **Discount Program**
        - 10% off on 3+ modifications
        - 5% loyalty discount for returning customers
        - Free basic car wash with every modification
        
        ⭐ **Loyalty Rewards**
        - Earn 1 point for every ₹100 spent
        - Redeem points for discounts
        - Priority scheduling
        
        📅 **Current Promotions**
        - Free installation on audio systems this month
        - 15% off on ceramic coating packages
        """)
    
    st.markdown("---")
    
    # Quick Stats
    st.subheader("🏆 Studio Statistics")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total_customers FROM customers")
    total_customers = cursor.fetchone()['total_customers']
    
    cursor.execute("SELECT COUNT(*) as total_bills FROM bills")
    total_bills = cursor.fetchone()['total_bills']
    
    cursor.execute("SELECT SUM(total) as total_revenue FROM bills")
    total_revenue = cursor.fetchone()['total_revenue'] or 0
    
    cursor.execute("SELECT COUNT(*) as total_mods FROM modifications WHERE is_active = 1")
    total_mods = cursor.fetchone()['total_mods']
    
    conn.close()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Happy Customers", total_customers)
    with col2:
        st.metric("Projects Completed", total_bills)
    with col3:
        st.metric("Total Revenue", f"₹{total_revenue:,.2f}")
    with col4:
        st.metric("Available Mods", total_mods)

# Build Page
def build_page():
    if not st.session_state.user_email:
        st.warning("Please login or register to start a build")
        if st.button("Go to Login", type="primary"):
            st.session_state.current_page = "auth"
            st.rerun()
        return
    
    st.title("🔧 New Build Configuration")
    
    # Get customer's cars
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT car_id, car_model, car_make, car_year FROM cars WHERE customer_email = ?", 
                   (st.session_state.user_email,))
    cars = cursor.fetchall()
    
    if not cars:
        st.info("You haven't added any cars yet. Let's add one first!")
        
        with st.expander("➕ Add New Car", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                car_model = st.text_input("Car Model*")
                car_make = st.text_input("Car Make")
                car_year = st.number_input("Year", min_value=1900, max_value=datetime.now().year + 1, step=1)
            with col2:
                car_color = st.text_input("Current Color")
                registration_date = st.date_input("Registration Date")
            
            if st.button("Add Car", type="primary"):
                if not car_model:
                    st.error("Car Model is required")
                else:
                    cursor.execute("""
                        INSERT INTO cars (customer_email, car_model, car_make, car_year, car_color) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (st.session_state.user_email, car_model, car_make, car_year, car_color))
                    conn.commit()
                    st.success(f"Car '{car_model}' added successfully!")
                    st.rerun()
    else:
        # Car selection
        car_options = [f"{car['car_model']} ({car['car_make'] or 'N/A'} - {car['car_year'] or 'N/A'})" 
                      for car in cars]
        selected_car_idx = st.selectbox("Select your car:", range(len(car_options)), 
                                       format_func=lambda x: car_options[x])
        
        st.session_state.selected_car = cars[selected_car_idx]
        
        st.markdown(f"### Selected Car: **{cars[selected_car_idx]['car_model']}**")
        
        # Add new car option
        with st.expander("➕ Add Another Car"):
            col1, col2 = st.columns(2)
            with col1:
                new_car_model = st.text_input("Car Model")
                new_car_make = st.text_input("Car Make")
            with col2:
                new_car_year = st.number_input("Year", min_value=1900, max_value=datetime.now().year + 1, step=1, key="new_year")
                new_car_color = st.text_input("Current Color", key="new_color")
            
            if st.button("Add New Car"):
                if new_car_model:
                    cursor.execute("""
                        INSERT INTO cars (customer_email, car_model, car_make, car_year, car_color) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (st.session_state.user_email, new_car_model, new_car_make, new_car_year, new_car_color))
                    conn.commit()
                    st.success(f"Car '{new_car_model}' added successfully!")
                    st.rerun()
    
    # Get modifications
    cursor.execute("SELECT mod_id, name, price, category, description FROM modifications WHERE category != 'Color' AND is_active = 1 ORDER BY category, price DESC")
    modifications = cursor.fetchall()
    
    # Get colors
    cursor.execute("SELECT mod_id, name, price, description FROM modifications WHERE category = 'Color' AND is_active = 1 ORDER BY price DESC")
    colors = cursor.fetchall()
    
    conn.close()
    
    st.markdown("---")
    
    # Modifications selection
    st.subheader("📋 Select Modifications")
    
    # Group modifications by category
    categories = {}
    for mod in modifications:
        category = mod['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(dict(mod))
    
    # Create tabs for each category
    tabs = st.tabs([f"🏎️ {cat}" for cat in categories.keys()])
    
    selected_mods_ids = []
    
    for tab, (category, mods_list) in zip(tabs, categories.items()):
        with tab:
            cols = st.columns(2)
            for idx, mod in enumerate(mods_list):
                col_idx = idx % 2
                with cols[col_idx]:
                    is_selected = any(m['mod_id'] == mod['mod_id'] for m in st.session_state.selected_mods)
                    
                    st.markdown(f"""
                    <div class="mod-card {'selected' if is_selected else ''}">
                        <h4>{mod['name']}</h4>
                        <p class="price-tag">₹{mod['price']:,.2f}</p>
                        <p><small>{mod['description'] or 'No description'}</small></p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if is_selected:
                        if st.button(f"❌ Remove", key=f"remove_{mod['mod_id']}"):
                            st.session_state.selected_mods = [
                                m for m in st.session_state.selected_mods 
                                if m['mod_id'] != mod['mod_id']
                            ]
                            st.rerun()
                    else:
                        if st.button(f"✅ Select", key=f"select_{mod['mod_id']}"):
                            st.session_state.selected_mods.append(mod)
                            st.rerun()
    
    st.markdown("---")
    
    # Color selection
    st.subheader("🎨 Select Color (Optional)")
    
    if colors:
        color_cols = st.columns(3)
        for idx, color in enumerate(colors):
            with color_cols[idx % 3]:
                is_selected = st.session_state.selected_color and st.session_state.selected_color['mod_id'] == color['mod_id']
                
                st.markdown(f"""
                <div class="mod-card {'selected' if is_selected else ''}">
                    <h4>{color['name']}</h4>
                    <p class="price-tag">₹{color['price']:,.2f}</p>
                    <p><small>{color['description'] or 'No description'}</small></p>
                </div>
                """, unsafe_allow_html=True)
                
                if is_selected:
                    if st.button(f"❌ Remove Color", key=f"remove_color_{color['mod_id']}"):
                        st.session_state.selected_color = None
                        st.rerun()
                else:
                    if st.button(f"🎨 Select Color", key=f"select_color_{color['mod_id']}"):
                        st.session_state.selected_color = color
                        st.rerun()
    else:
        st.info("No colors available at the moment")
    
    st.markdown("---")
    
    # Summary and calculations
    st.subheader("💰 Price Summary")
    
    totals = calculate_totals(st.session_state.selected_mods, 
                             st.session_state.selected_color,
                             st.session_state.user_email)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Selected Items")
        
        if st.session_state.selected_mods:
            for mod in st.session_state.selected_mods:
                st.write(f"• {mod['name']} - ₹{mod['price']:,.2f}")
        else:
            st.info("No modifications selected")
        
        if st.session_state.selected_color:
            st.write(f"• 🎨 {st.session_state.selected_color['name']} - ₹{st.session_state.selected_color['price']:,.2f}")
    
    with col2:
        st.markdown("### Cost Breakdown")
        
        st.write(f"**Subtotal:** ₹{totals['subtotal']:,.2f}")
        
        if totals['discount_percent'] > 0:
            st.write(f"**Discount ({totals['discount_percent']}%):** -₹{totals['discount_amount']:,.2f}")
            st.write(f"**Subtotal after discount:** ₹{totals['subtotal_after_discount']:,.2f}")
        
        st.write(f"**GST (18%):** ₹{totals['gst']:,.2f}")
        st.markdown(f"### **Total:** ₹{totals['total']:,.2f}")
    
    st.markdown("---")
    
    # Payment and finalization
    if st.session_state.selected_mods or st.session_state.selected_color:
        st.subheader("💳 Complete Your Build")
        
        col1, col2 = st.columns(2)
        
        with col1:
            payment_method = st.selectbox("Payment Method", 
                                         ["Cash", "Credit Card", "Debit Card", "UPI", "Net Banking"])
            notes = st.text_area("Special Notes (Optional)")
        
        with col2:
            # Loyalty points info
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT loyalty_points FROM customers WHERE email = ?", 
                          (st.session_state.user_email,))
            loyalty_points = cursor.fetchone()['loyalty_points']
            conn.close()
            
            st.info(f"""
            **Loyalty Information:**
            - Current points: {loyalty_points}
            - Points to be earned: {int(totals['total'] / 100)}
            - Total points after purchase: {loyalty_points + int(totals['total'] / 100)}
            """)
        
        if st.button("✅ Generate Bill & Complete Purchase", type="primary", use_container_width=True):
            if not st.session_state.selected_car:
                st.error("Please select a car first")
            else:
                # Save bill to database
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Generate bill ID and number
                bill_id = f"BILL-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
                bill_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Get next bill number
                cursor.execute("SELECT MAX(bill_number) FROM bills")
                result = cursor.fetchone()[0]
                bill_number = (result or 0) + 1
                
                # Save bill
                cursor.execute("""
                    INSERT INTO bills (bill_id, customer_email, car_id, bill_date, bill_number, 
                                     subtotal, discount, discount_percent, gst, gst_rate, total, 
                                     payment_method, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (bill_id, st.session_state.user_email, 
                     st.session_state.selected_car['car_id'], bill_date, bill_number,
                     totals['subtotal'], totals['discount_amount'], totals['discount_percent'], 
                     totals['gst'], GST_RATE, totals['total'], payment_method, notes))
                
                # Save bill items
                for mod in st.session_state.selected_mods:
                    cursor.execute("""
                        INSERT INTO bill_items (bill_id, mod_id, mod_name, mod_category, price, total_price)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (bill_id, mod['mod_id'], mod['name'], mod['category'], mod['price'], mod['price']))
                
                if st.session_state.selected_color:
                    cursor.execute("""
                        INSERT INTO bill_items (bill_id, mod_id, mod_name, mod_category, price, total_price)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (bill_id, st.session_state.selected_color['mod_id'], 
                         st.session_state.selected_color['name'], 'Color',
                         st.session_state.selected_color['price'], st.session_state.selected_color['price']))
                
                # Update customer
                cursor.execute("""
                    UPDATE customers 
                    SET total_visits = total_visits + 1,
                        total_spent = total_spent + ?,
                        last_visit = CURRENT_TIMESTAMP,
                        loyalty_points = loyalty_points + ?
                    WHERE email = ?
                """, (totals['total'], int(totals['total'] / 100), st.session_state.user_email))
                
                conn.commit()
                
                # Generate bill file
                bill_filename = f"bills/{datetime.now().strftime('%Y%m%d')}_{bill_number}_{safe_text(st.session_state.user_name)}.txt"
                
                bill_content = f"""
{'='*70}
{'CUSTOM CAR MODIFICATION STUDIO':^70}
{'='*70}
{'Bill No:':<15} {bill_number}
{'Bill ID:':<15} {bill_id}
{'Date:':<15} {bill_date}
{'='*70}
{'Customer:':<15} {st.session_state.user_name}
{'Email:':<15} {st.session_state.user_email}
{'Car:':<15} {st.session_state.selected_car['car_model']}
{'Payment:':<15} {payment_method}
{'='*70}
{'MODIFICATIONS':^70}
{'-'*70}
"""
                
                item_no = 1
                for mod in st.session_state.selected_mods:
                    bill_content += f"{item_no:<5} {mod['name']:<40} ₹{mod['price']:>8.2f} ₹{mod['price']:>8.2f}\n"
                    item_no += 1
                
                if st.session_state.selected_color:
                    bill_content += f"{item_no:<5} Paint - {st.session_state.selected_color['name']:<34} ₹{st.session_state.selected_color['price']:>8.2f} ₹{st.session_state.selected_color['price']:>8.2f}\n"
                
                bill_content += f"""
{'-'*70}
{'Subtotal:':<55} ₹{totals['subtotal']:>10.2f}
{'Discount:':<55} -₹{totals['discount_amount']:>10.2f}
{'GST (18%):':<55} ₹{totals['gst']:>10.2f}
{'='*70}
{'TOTAL AMOUNT:':<55} ₹{totals['total']:>10.2f}
{'='*70}
Thank you for your business!
Visit again for more modifications!
"""
                
                with open(bill_filename, 'w', encoding='utf-8') as f:
                    f.write(bill_content)
                
                conn.close()
                
                st.session_state.build_complete = True
                st.session_state.last_bill = {
                    'bill_id': bill_id,
                    'bill_number': bill_number,
                    'total': totals['total'],
                    'date': bill_date,
                    'filename': bill_filename
                }
                
                st.success("✅ Purchase completed successfully!")
                st.balloons()
                
                # Show bill summary
                st.markdown(f"""
                <div class="success-box">
                    <h3>🎉 Build Complete!</h3>
                    <p><strong>Bill Number:</strong> {bill_number}</p>
                    <p><strong>Bill ID:</strong> {bill_id}</p>
                    <p><strong>Total Amount:</strong> ₹{totals['total']:,.2f}</p>
                    <p><strong>Date:</strong> {bill_date}</p>
                    <p><strong>Car:</strong> {st.session_state.selected_car['car_model']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Download button for bill
                with open(bill_filename, 'r', encoding='utf-8') as f:
                    bill_data = f.read()
                
                st.download_button(
                    label="📄 Download Bill",
                    data=bill_data,
                    file_name=f"bill_{bill_number}.txt",
                    mime="text/plain"
                )
                
                # Reset selections
                if st.button("🔄 Start New Build"):
                    st.session_state.selected_mods = []
                    st.session_state.selected_color = None
                    st.session_state.build_complete = False
                    st.rerun()

# Pricing Page
def pricing_page():
    st.title("💰 Modification Pricing")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all modifications grouped by category
    cursor.execute("""
        SELECT category, name, price, description 
        FROM modifications 
        WHERE is_active = 1 
        ORDER BY category, price DESC
    """)
    modifications = cursor.fetchall()
    
    # Group by category
    categories = {}
    for mod in modifications:
        category = mod['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(dict(mod))
    
    # Create tabs for each category
    tabs = st.tabs([f"🏷️ {cat}" for cat in categories.keys()])
    
    for tab, (category, mods_list) in zip(tabs, categories.items()):
        with tab:
            st.markdown(f"### {category} Modifications")
            
            for mod in mods_list:
                with st.expander(f"{mod['name']} - ₹{mod['price']:,.2f}"):
                    st.write(f"**Price:** ₹{mod['price']:,.2f}")
                    if mod['description']:
                        st.write(f"**Description:** {mod['description']}")
    
    conn.close()
    
    st.markdown("---")
    
    # Discount information
    st.subheader("🎁 Discounts & Offers")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Volume Discounts
        - **10% discount** on 3 or more modifications
        - **15% discount** on 5 or more modifications
        - **20% discount** on full package (all categories)
        """)
    
    with col2:
        st.markdown("""
        ### Loyalty Program
        - **5% loyalty discount** for returning customers
        - **Earn 1 point** for every ₹100 spent
        - **Redeem points** for future discounts
        - **Priority scheduling** for loyal customers
        """)
    
    st.markdown("---")
    
    # Price comparison chart
    if categories:
        st.subheader("📊 Price Comparison by Category")
        
        # Prepare data for chart
        chart_data = []
        for category, mods_list in categories.items():
            for mod in mods_list:
                chart_data.append({
                    'Category': category,
                    'Modification': mod['name'],
                    'Price': mod['price']
                })
        
        df = pd.DataFrame(chart_data)
        
        # Create box plot
        fig = px.box(df, x='Category', y='Price', 
                     title='Price Distribution by Category',
                     color='Category')
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

# Profile Page
def profile_page():
    if not st.session_state.user_email:
        st.warning("Please login to view your profile")
        if st.button("Go to Login", type="primary"):
            st.session_state.current_page = "auth"
            st.rerun()
        return
    
    st.title("👤 Your Profile")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get customer info
    cursor.execute("""
        SELECT name, email, phone, address, city, state, pincode,
               total_visits, total_spent, loyalty_points,
               first_visit, last_visit
        FROM customers
        WHERE email = ?
    """, (st.session_state.user_email,))
    customer = cursor.fetchone()
    
    if customer:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("### Personal Information")
            st.write(f"**Name:** {customer['name']}")
            st.write(f"**Email:** {customer['email']}")
            st.write(f"**Phone:** {customer['phone'] or 'Not provided'}")
            st.write(f"**Address:** {customer['address'] or 'Not provided'}")
            st.write(f"**City:** {customer['city'] or 'Not provided'}")
            st.write(f"**State:** {customer['state'] or 'Not provided'}")
            st.write(f"**Pincode:** {customer['pincode'] or 'Not provided'}")
        
        with col2:
            st.markdown("### Statistics")
            
            col2a, col2b, col2c = st.columns(3)
            with col2a:
                st.metric("Total Visits", customer['total_visits'])
            with col2b:
                st.metric("Total Spent", f"₹{customer['total_spent']:,.2f}")
            with col2c:
                st.metric("Loyalty Points", customer['loyalty_points'])
            
            st.write(f"**First Visit:** {customer['first_visit']}")
            st.write(f"**Last Visit:** {customer['last_visit']}")
            
            # Loyalty progress
            st.markdown("### Loyalty Progress")
            progress = min(customer['loyalty_points'] / 100, 1.0)
            st.progress(progress)
            st.caption(f"{customer['loyalty_points']} points (100 points needed for next reward)")
    
    st.markdown("---")
    
    # Customer's cars
    st.subheader("🚗 Your Cars")
    
    cursor.execute("""
        SELECT car_model, car_make, car_year, car_color
        FROM cars
        WHERE customer_email = ?
        ORDER BY car_year DESC
    """, (st.session_state.user_email,))
    
    cars = cursor.fetchall()
    
    if cars:
        for i, car in enumerate(cars):
            with st.expander(f"Car {i+1}: {car['car_model']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Model:** {car['car_model']}")
                    st.write(f"**Make:** {car['car_make'] or 'N/A'}")
                with col2:
                    st.write(f"**Year:** {car['car_year'] or 'N/A'}")
                    st.write(f"**Color:** {car['car_color'] or 'N/A'}")
    else:
        st.info("You haven't added any cars yet.")
        if st.button("➕ Add Your First Car"):
            st.session_state.current_page = "build"
            st.rerun()
    
    st.markdown("---")
    
    # Recent purchases
    st.subheader("📜 Recent Purchases")
    
    cursor.execute("""
        SELECT b.bill_id, b.bill_date, b.total, b.payment_method, c.car_model
        FROM bills b
        LEFT JOIN cars c ON b.car_id = c.car_id
        WHERE b.customer_email = ?
        ORDER BY b.bill_date DESC
        LIMIT 10
    """, (st.session_state.user_email,))
    
    recent_bills = cursor.fetchall()
    
    if recent_bills:
        for bill in recent_bills:
            with st.expander(f"Bill {bill['bill_id']} - ₹{bill['total']:,.2f}"):
                st.write(f"**Date:** {bill['bill_date']}")
                st.write(f"**Amount:** ₹{bill['total']:,.2f}")
                st.write(f"**Car:** {bill['car_model']}")
                st.write(f"**Payment:** {bill['payment_method']}")
    else:
        st.info("No purchases yet. Start your first build!")
    
    conn.close()

# Appointments Page
def appointments_page():
    if not st.session_state.user_email:
        st.warning("Please login to manage appointments")
        if st.button("Go to Login", type="primary"):
            st.session_state.current_page = "auth"
            st.rerun()
        return
    
    st.title("📅 Appointments")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tab1, tab2 = st.tabs(["Schedule New", "View Appointments"])
    
    with tab1:
        st.subheader("📝 Schedule New Appointment")
        
        # Get customer's cars
        cursor.execute("SELECT car_id, car_model FROM cars WHERE customer_email = ?", 
                      (st.session_state.user_email,))
        cars = cursor.fetchall()
        
        if not cars:
            st.warning("Please add a car first before scheduling an appointment.")
            if st.button("Add Car Now"):
                st.session_state.current_page = "build"
                st.rerun()
        else:
            car_options = {f"{car['car_model']}": car['car_id'] for car in cars}
            selected_car = st.selectbox("Select Car", list(car_options.keys()))
            car_id = car_options[selected_car]
            
            col1, col2 = st.columns(2)
            with col1:
                appointment_date = st.date_input("Appointment Date", 
                                                min_value=datetime.now().date())
                service_type = st.selectbox("Service Type", 
                                           ["Modification", "Consultation", "Maintenance", 
                                            "Repair", "Inspection", "Other"])
            with col2:
                appointment_time = st.time_input("Appointment Time")
                notes = st.text_area("Special Notes")
            
            if st.button("Schedule Appointment", type="primary"):
                if appointment_date < datetime.now().date():
                    st.error("Appointment date cannot be in the past")
                else:
                    cursor.execute("""
                        INSERT INTO appointments (customer_email, car_id, appointment_date, 
                                                appointment_time, service_type, notes, status)
                        VALUES (?, ?, ?, ?, ?, ?, 'Scheduled')
                    """, (st.session_state.user_email, car_id, 
                         appointment_date.strftime("%Y-%m-%d"),
                         appointment_time.strftime("%H:%M"), service_type, notes))
                    
                    conn.commit()
                    st.success("✅ Appointment scheduled successfully!")
    
    with tab2:
        st.subheader("📋 Your Appointments")
        
        # Filter options
        filter_option = st.radio("Filter by:", ["Upcoming", "Past", "All"])
        
        if filter_option == "Upcoming":
            cursor.execute("""
                SELECT a.*, c.car_model
                FROM appointments a
                LEFT JOIN cars c ON a.car_id = c.car_id
                WHERE a.customer_email = ? AND a.appointment_date >= DATE('now')
                ORDER BY a.appointment_date, a.appointment_time
            """, (st.session_state.user_email,))
        elif filter_option == "Past":
            cursor.execute("""
                SELECT a.*, c.car_model
                FROM appointments a
                LEFT JOIN cars c ON a.car_id = c.car_id
                WHERE a.customer_email = ? AND a.appointment_date < DATE('now')
                ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """, (st.session_state.user_email,))
        else:
            cursor.execute("""
                SELECT a.*, c.car_model
                FROM appointments a
                LEFT JOIN cars c ON a.car_id = c.car_id
                WHERE a.customer_email = ?
                ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """, (st.session_state.user_email,))
        
        appointments = cursor.fetchall()
        
        if appointments:
            for appt in appointments:
                with st.expander(f"{appt['appointment_date']} - {appt['service_type']} - {appt['status']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Date:** {appt['appointment_date']}")
                        st.write(f"**Time:** {appt['appointment_time']}")
                        st.write(f"**Car:** {appt['car_model']}")
                    with col2:
                        st.write(f"**Service:** {appt['service_type']}")
                        st.write(f"**Status:** {appt['status']}")
                        if appt['notes']:
                            st.write(f"**Notes:** {appt['notes']}")
        else:
            st.info("No appointments found.")
    
    conn.close()

# Reports Page
def reports_page():
    if not st.session_state.user_email:
        st.warning("Please login to view reports")
        if st.button("Go to Login", type="primary"):
            st.session_state.current_page = "auth"
            st.rerun()
        return
    
    st.title("📊 Your Reports")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tab1, tab2, tab3 = st.tabs(["Spending Analysis", "Modification Trends", "Loyalty Status"])
    
    with tab1:
        st.subheader("💰 Spending Analysis")
        
        # Monthly spending
        cursor.execute("""
            SELECT strftime('%Y-%m', bill_date) as month,
                   COUNT(*) as bills,
                   SUM(total) as total_spent,
                   AVG(total) as avg_bill
            FROM bills
            WHERE customer_email = ? AND bill_date >= DATE('now', '-6 months')
            GROUP BY strftime('%Y-%m', bill_date)
            ORDER BY month
        """, (st.session_state.user_email,))
        
        monthly_data = cursor.fetchall()
        
        if monthly_data:
            df_monthly = pd.DataFrame(monthly_data, columns=['Month', 'Bills', 'Total_Spent', 'Avg_Bill'])
            
            col1, col2 = st.columns(2)
            with col1:
                # Bar chart for monthly spending
                fig1 = px.bar(df_monthly, x='Month', y='Total_Spent',
                             title='Monthly Spending',
                             labels={'Total_Spent': 'Amount (₹)', 'Month': 'Month'},
                             color='Total_Spent')
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                # Line chart for average bill
                fig2 = px.line(df_monthly, x='Month', y='Avg_Bill',
                              title='Average Bill Amount Trend',
                              labels={'Avg_Bill': 'Average Bill (₹)', 'Month': 'Month'},
                              markers=True)
                st.plotly_chart(fig2, use_container_width=True)
            
            # Statistics
            st.subheader("📈 Spending Statistics")
            col1, col2, col3 = st.columns(3)
            
            total_spent = df_monthly['Total_Spent'].sum()
            avg_monthly = df_monthly['Total_Spent'].mean()
            max_month = df_monthly.loc[df_monthly['Total_Spent'].idxmax()]
            
            with col1:
                st.metric("Total Spent (6 months)", f"₹{total_spent:,.2f}")
            with col2:
                st.metric("Average Monthly", f"₹{avg_monthly:,.2f}")
            with col3:
                st.metric("Highest Month", f"{max_month['Month']}: ₹{max_month['Total_Spent']:,.2f}")
        else:
            st.info("No spending data available for the last 6 months.")
    
    with tab2:
        st.subheader("🔧 Modification Trends")
        
        # Popular modifications
        cursor.execute("""
            SELECT bi.mod_category, bi.mod_name, COUNT(*) as times_purchased,
                   SUM(bi.total_price) as total_spent
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.bill_id
            WHERE b.customer_email = ?
            GROUP BY bi.mod_category, bi.mod_name
            ORDER BY times_purchased DESC
        """, (st.session_state.user_email,))
        
        mod_data = cursor.fetchall()
        
        if mod_data:
            df_mods = pd.DataFrame(mod_data, 
                                  columns=['Category', 'Modification', 'Times_Purchased', 'Total_Spent'])
            
            col1, col2 = st.columns(2)
            with col1:
                # Pie chart for categories
                fig3 = px.pie(df_mods, names='Category', values='Total_Spent',
                             title='Spending by Category')
                st.plotly_chart(fig3, use_container_width=True)
            
            with col2:
                # Bar chart for top modifications
                top_mods = df_mods.nlargest(10, 'Total_Spent')
                fig4 = px.bar(top_mods, x='Modification', y='Total_Spent',
                             title='Top 10 Modifications by Spending',
                             labels={'Total_Spent': 'Amount (₹)', 'Modification': 'Modification'})
                fig4.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig4, use_container_width=True)
            
            # Data table
            st.subheader("📋 All Modifications")
            st.dataframe(df_mods, use_container_width=True)
        else:
            st.info("No modification data available.")
    
    with tab3:
        st.subheader("⭐ Loyalty Status")
        
        # Get loyalty points and history
        cursor.execute("""
            SELECT loyalty_points, total_visits, total_spent
            FROM customers WHERE email = ?
        """, (st.session_state.user_email,))
        
        loyalty_data = cursor.fetchone()
        
        if loyalty_data:
            points = loyalty_data['loyalty_points']
            visits = loyalty_data['total_visits']
            spent = loyalty_data['total_spent']
            
            # Loyalty tiers
            tiers = [
                {"name": "Bronze", "points": 0, "color": "#CD7F32"},
                {"name": "Silver", "points": 100, "color": "#C0C0C0"},
                {"name": "Gold", "points": 500, "color": "#FFD700"},
                {"name": "Platinum", "points": 1000, "color": "#E5E4E2"}
            ]
            
            # Determine current tier
            current_tier = "Bronze"
            next_tier = "Silver"
            points_to_next = 100 - points
            
            for i in range(len(tiers) - 1):
                if points >= tiers[i]['points'] and points < tiers[i + 1]['points']:
                    current_tier = tiers[i]['name']
                    next_tier = tiers[i + 1]['name']
                    points_to_next = tiers[i + 1]['points'] - points
                    break
            if points >= tiers[-1]['points']:
                current_tier = tiers[-1]['name']
                next_tier = "Max"
                points_to_next = 0
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Current Points", points)
                st.metric("Current Tier", current_tier)
            
            with col2:
                st.metric("Next Tier", next_tier)
                st.metric("Points Needed", points_to_next if points_to_next > 0 else "Max")
            
            # Progress visualization
            st.subheader("🎯 Progress to Next Tier")
            
            max_points = 1000
            progress = min(points / max_points, 1.0)
            
            st.progress(progress)
            st.caption(f"{points} / {max_points} points")
            
            # Benefits by tier
            st.subheader("🎁 Tier Benefits")
            
            benefits_df = pd.DataFrame([
                {"Tier": "Bronze", "Discount": "5%", "Priority": "No", "Free Service": "No"},
                {"Tier": "Silver", "Discount": "7%", "Priority": "Yes", "Free Service": "Basic Wash"},
                {"Tier": "Gold", "Discount": "10%", "Priority": "Yes", "Free Service": "Full Detailing"},
                {"Tier": "Platinum", "Discount": "15%", "Priority": "VIP", "Free Service": "Annual Maintenance"}
            ])
            
            st.dataframe(benefits_df, use_container_width=True)
            
            # Points earning potential
            st.subheader("💡 How to Earn More Points")
            st.write("""
            - **₹100 spent** = 1 point
            - **Refer a friend** = 50 points
            - **Complete a full package** = 50 bonus points
            - **Annual maintenance** = 100 points
            """)
    
    conn.close()

# Export Page
def export_page():
    if not st.session_state.user_email:
        st.warning("Please login to export data")
        if st.button("Go to Login", type="primary"):
            st.session_state.current_page = "auth"
            st.rerun()
        return
    
    st.title("📤 Export Your Data")
    
    conn = get_db_connection()
    
    export_option = st.radio("Select data to export:", 
                            ["Purchase History", "Appointment History", "Complete Profile"])
    
    if st.button("📥 Generate Export", type="primary"):
        if export_option == "Purchase History":
            df = pd.read_sql_query("""
                SELECT b.bill_date, b.bill_id, b.total, b.payment_method,
                       c.car_model, bi.mod_name, bi.mod_category, bi.price
                FROM bills b
                LEFT JOIN cars c ON b.car_id = c.car_id
                LEFT JOIN bill_items bi ON b.bill_id = bi.bill_id
                WHERE b.customer_email = ?
                ORDER BY b.bill_date DESC
            """, conn, params=(st.session_state.user_email,))
            
        elif export_option == "Appointment History":
            df = pd.read_sql_query("""
                SELECT a.appointment_date, a.appointment_time, a.service_type,
                       a.status, a.notes, c.car_model
                FROM appointments a
                LEFT JOIN cars c ON a.car_id = c.car_id
                WHERE a.customer_email = ?
                ORDER BY a.appointment_date DESC
            """, conn, params=(st.session_state.user_email,))
        
        else:  # Complete Profile
            # Combine multiple queries
            profile_df = pd.read_sql_query("""
                SELECT name, email, phone, address, city, state, pincode,
                       total_visits, total_spent, loyalty_points,
                       first_visit, last_visit
                FROM customers
                WHERE email = ?
            """, conn, params=(st.session_state.user_email,))
            
            cars_df = pd.read_sql_query("""
                SELECT car_model, car_make, car_year, car_color
                FROM cars
                WHERE customer_email = ?
            """, conn, params=(st.session_state.user_email,))
            
            bills_df = pd.read_sql_query("""
                SELECT b.bill_date, b.bill_id, b.total, b.payment_method, c.car_model
                FROM bills b
                LEFT JOIN cars c ON b.car_id = c.car_id
                WHERE b.customer_email = ?
            """, conn, params=(st.session_state.user_email,))
            
            # Create Excel file with multiple sheets
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                profile_df.to_excel(writer, sheet_name='Profile', index=False)
                cars_df.to_excel(writer, sheet_name='Cars', index=False)
                bills_df.to_excel(writer, sheet_name='Purchases', index=False)
            
            output.seek(0)
            st.download_button(
                label="📥 Download Complete Profile (Excel)",
                data=output,
                file_name=f"car_mod_profile_{st.session_state.user_email}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            conn.close()
            return
        
        conn.close()
        
        # Convert to CSV
        csv = df.to_csv(index=False)
        
        # Offer download
        st.download_button(
            label=f"📥 Download {export_option} (CSV)",
            data=csv,
            file_name=f"car_mod_{export_option.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
        # Show preview
        st.subheader("📋 Data Preview")
        st.dataframe(df.head(10), use_container_width=True)

# Main app router
def main():
    if current_page == "home":
        home_page()
    elif current_page == "auth":
        auth_page()
    elif current_page == "build":
        build_page()
    elif current_page == "pricing":
        pricing_page()
    elif current_page == "profile":
        profile_page()
    elif current_page == "appointments":
        appointments_page()
    elif current_page == "reports":
        reports_page()
    elif current_page == "export":
        export_page()

if __name__ == "__main__":
    main()
