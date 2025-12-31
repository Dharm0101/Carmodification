import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import uuid
import os
import json
from io import BytesIO
import base64
import hashlib
import random
import warnings
warnings.filterwarnings('ignore')

# Try to import ML libraries, but handle gracefully if not available
try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics.pairwise import cosine_similarity
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    # Create dummy classes to avoid errors
    class KMeans:
        def __init__(self, *args, **kwargs):
            pass
        def fit_predict(self, X):
            return [0] * len(X)
    class StandardScaler:
        def fit_transform(self, X):
            return X
    def cosine_similarity(a, b):
        return 0.5

# Constants
GST_RATE = 0.18
DB_NAME = "car_mod.db"

# Initialize session state
def init_session_state():
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
    if 'view_cart' not in st.session_state:
        st.session_state.view_cart = False
    if 'notifications' not in st.session_state:
        st.session_state.notifications = []
    if 'dark_mode' not in st.session_state:
        st.session_state.dark_mode = False
    if 'admin_mode' not in st.session_state:
        st.session_state.admin_mode = False
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "home"

init_session_state()

# Database connection helper
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# Create necessary directories
os.makedirs("bills", exist_ok=True)
os.makedirs("exports", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

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

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_referral_code(email):
    return hashlib.md5(email.encode()).hexdigest()[:8].upper()

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
    
    # Volume discount
    if len(mods) >= 5:
        discount_percent += 15
    elif len(mods) >= 3:
        discount_percent += 10
    
    # Loyalty discount
    if customer_email:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT total_visits, loyalty_points FROM customers WHERE email = ?", (customer_email,))
        customer = cursor.fetchone()
        conn.close()
        
        if customer:
            if customer['total_visits'] > 5:
                discount_percent += 10
            elif customer['total_visits'] > 1:
                discount_percent += 5
    
    # Festival discount (seasonal)
    current_month = datetime.now().month
    festival_months = [1, 10, 12]  # Jan (New Year), Oct (Diwali), Dec (Christmas)
    if current_month in festival_months:
        discount_percent += 5
    
    # Cap discount at 30%
    discount_percent = min(discount_percent, 30)
    
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
        background-color: white;
        transition: all 0.3s;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    .mod-card:hover {
        border-color: #667eea;
        box-shadow: 0 4px 8px rgba(102, 126, 234, 0.15);
        transform: translateY(-2px);
    }
    .mod-card.selected {
        border-color: #667eea;
        background: linear-gradient(135deg, #667eea10 0%, #764ba210 100%);
        box-shadow: 0 6px 12px rgba(102, 126, 234, 0.2);
    }
    .price-tag {
        font-weight: bold;
        color: #764ba2;
        font-size: 1.2em;
    }
    .discount-badge {
        background-color: #28a745;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
        margin-left: 8px;
    }
    .stButton button {
        width: 100%;
        transition: all 0.3s;
        border-radius: 8px;
    }
    .stButton button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
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
    .notification-badge {
        position: absolute;
        top: -5px;
        right: -5px;
        background-color: #dc3545;
        color: white;
        border-radius: 50%;
        width: 20px;
        height: 20px;
        font-size: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .feature-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 1px solid #dee2e6;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    .car-3d-view {
        border: 2px solid #dee2e6;
        border-radius: 10px;
        overflow: hidden;
        margin: 1rem 0;
    }
    .risk-high { color: #dc3545; font-weight: bold; }
    .risk-medium { color: #ffc107; font-weight: bold; }
    .risk-low { color: #28a745; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Notification system
def add_notification(message, type="info"):
    """Add notification to session state"""
    notification = {
        "id": len(st.session_state.notifications),
        "message": message,
        "type": type,
        "time": datetime.now().strftime("%H:%M"),
        "read": False
    }
    st.session_state.notifications.insert(0, notification)

def show_notifications():
    """Display notifications dropdown"""
    with st.sidebar:
        if st.session_state.notifications:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader("🔔 Notifications")
            with col2:
                if st.button("Clear All"):
                    st.session_state.notifications = []
                    st.rerun()
            
            unread_count = sum(1 for n in st.session_state.notifications if not n["read"])
            if unread_count > 0:
                st.info(f"{unread_count} unread notifications")
            
            for notification in st.session_state.notifications[:5]:
                icon = "🔵" if notification["type"] == "info" else "🟢" if notification["type"] == "success" else "🔴"
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"{icon} {notification['message']}")
                    st.caption(f"{notification['time']}")
                with col2:
                    if not notification["read"] and st.button("✓", key=f"read_{notification['id']}"):
                        notification["read"] = True
                        st.rerun()

# Enhanced Header
def show_header():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="main-header">
            <h1>🚗 Custom Car Modification Studio</h1>
            <p>Transform your vehicle with premium modifications</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Top navigation bar
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.current_page = "home"
            st.rerun()
    with col2:
        if st.button("🔧 Build", use_container_width=True):
            st.session_state.current_page = "build"
            st.rerun()
    with col3:
        cart_count = len(st.session_state.selected_mods) + (1 if st.session_state.selected_color else 0)
        if st.button(f"🛒 Cart ({cart_count})", use_container_width=True):
            st.session_state.view_cart = True
            st.rerun()
    with col4:
        if st.button("🤖 AI Rec", use_container_width=True):
            st.session_state.current_page = "ai_recommend"
            st.rerun()
    with col5:
        if st.button("⚠️ Risk", use_container_width=True):
            st.session_state.current_page = "risk_analysis"
            st.rerun()

# Enhanced Sidebar
def show_sidebar():
    with st.sidebar:
        if st.session_state.user_email:
            # User profile section
            st.markdown(f"""
            <div style="text-align: center; padding: 1rem; background: #f8f9fa; border-radius: 10px;">
                <h4>👤 {st.session_state.user_name}</h4>
                <p>{st.session_state.user_email}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Quick stats
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
                    st.metric("🏢 Visits", stats['total_visits'])
                    st.metric("⭐ Points", stats['loyalty_points'])
                with col2:
                    st.metric("💰 Spent", f"₹{stats['total_spent']:.2f}")
            
            st.markdown("---")
        
        # Navigation
        st.subheader("📱 Navigation")
        
        if st.session_state.user_email:
            menu_items = [
                ("🏠 Dashboard", "home"),
                ("🔧 Build & Configure", "build"),
                ("💰 Pricing", "pricing"),
                ("📊 Analytics", "reports"),
                ("📅 Appointments", "appointments"),
                ("👤 Profile", "profile"),
                ("👥 Customer Type", "customer_class"),
                ("📤 Export Data", "export"),
                ("⚙️ Settings", "settings")
            ]
        else:
            menu_items = [
                ("🏠 Home", "home"),
                ("💰 Pricing", "pricing"),
                ("🔐 Login/Register", "auth")
            ]
        
        for item_name, item_page in menu_items:
            if st.button(item_name, use_container_width=True):
                st.session_state.current_page = item_page
                st.rerun()
        
        st.markdown("---")
        
        # Quick actions
        if st.session_state.user_email:
            st.subheader("⚡ Quick Actions")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📋 New Build", use_container_width=True):
                    st.session_state.current_page = "build"
                    st.rerun()
                if st.button("📅 Book", use_container_width=True):
                    st.session_state.current_page = "appointments"
                    st.rerun()
            with col2:
                if st.button("🎮 3D View", use_container_width=True):
                    st.session_state.current_page = "preview"
                    st.rerun()
                if st.button("🚪 Logout", use_container_width=True, type="secondary"):
                    st.session_state.user_email = None
                    st.session_state.user_name = None
                    st.session_state.selected_mods = []
                    st.session_state.selected_color = None
                    st.session_state.selected_car = None
                    add_notification("Logged out successfully", "info")
                    st.rerun()
        
        # Show notifications
        if st.session_state.user_email and len(st.session_state.notifications) > 0:
            show_notifications()

# 1. AI RECOMMENDATION ENGINE
class AIRecommendationEngine:
    def __init__(self):
        self.conn = get_db_connection()
        
    def get_user_preferences(self, user_email):
        """Extract user preferences from purchase history"""
        cursor = self.conn.cursor()
        
        # Get user's purchase history
        cursor.execute("""
            SELECT bi.mod_category, COUNT(*) as frequency, 
                   AVG(bi.price) as avg_spent
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.bill_id
            WHERE b.customer_email = ?
            GROUP BY bi.mod_category
        """, (user_email,))
        
        preferences = cursor.fetchall()
        
        # Get user's car info
        cursor.execute("""
            SELECT car_model, car_make, car_year 
            FROM cars 
            WHERE customer_email = ?
            LIMIT 1
        """, (user_email,))
        car_info = cursor.fetchone()
        
        return preferences, car_info
    
    def get_all_modifications(self):
        """Get all available modifications"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT mod_id, name, price, category, description
            FROM modifications 
            WHERE is_active = 1
        """)
        return cursor.fetchall()
    
    def calculate_modification_score(self, mod, user_prefs, car_info):
        """Calculate AI score for a modification (0-100)"""
        score = 50  # Base score
        
        # 1. Category preference boost
        for pref in user_prefs:
            if pref['mod_category'] == mod['category']:
                score += pref['frequency'] * 5  # More purchases = higher preference
        
        # 2. Price range suitability
        total_spent = sum(p['avg_spent'] for p in user_prefs)
        avg_spent = total_spent / len(user_prefs) if user_prefs else 0
        
        if avg_spent > 0:
            price_ratio = mod['price'] / (avg_spent * 1.5)
            if 0.5 <= price_ratio <= 1.5:  # Within comfortable price range
                score += 20
            elif price_ratio < 0.5:  # Cheaper than usual
                score += 10
            else:  # More expensive
                score -= 10
        
        # 3. Car model compatibility
        if car_info:
            car_age = datetime.now().year - (car_info['car_year'] or datetime.now().year)
            
            # Performance mods for newer cars
            if mod['category'] == 'Performance' and car_age < 5:
                score += 10
            
            # Safety mods for older cars
            if mod['category'] == 'Safety' and car_age > 5:
                score += 10
        
        return min(max(score, 0), 100)  # Clamp between 0-100
    
    def get_personalized_recommendations(self, user_email, limit=5):
        """Get AI-powered personalized recommendations"""
        user_prefs, car_info = self.get_user_preferences(user_email)
        all_mods = self.get_all_modifications()
        
        recommendations = []
        for mod in all_mods:
            score = self.calculate_modification_score(mod, user_prefs, car_info)
            
            if score >= 60:  # Only recommend if score > 60%
                recommendations.append({
                    'mod_id': mod['mod_id'],
                    'name': mod['name'],
                    'category': mod['category'],
                    'price': mod['price'],
                    'ai_score': score,
                    'reason': self.generate_recommendation_reason(mod, user_prefs, car_info, score)
                })
        
        # Sort by AI score and return top N
        recommendations.sort(key=lambda x: x['ai_score'], reverse=True)
        return recommendations[:limit]
    
    def generate_recommendation_reason(self, mod, user_prefs, car_info, score):
        """Generate human-readable reason for recommendation"""
        reasons = []
        
        # Category preference reason
        for pref in user_prefs:
            if pref['mod_category'] == mod['category']:
                reasons.append(f"Matches your preference for {mod['category']} modifications")
                break
        
        # Price reason
        if mod['price'] < 1000:
            reasons.append("Budget-friendly option")
        elif mod['price'] > 3000:
            reasons.append("Premium upgrade for enhanced experience")
        
        # Car compatibility reason
        if car_info:
            if mod['category'] == 'Performance' and car_info.get('car_year', 0) > 2020:
                reasons.append("Ideal for newer car models")
        
        return " | ".join(reasons[:2]) if reasons else "Great value addition"
    
    def __del__(self):
        self.conn.close()

# 2. MODIFICATION RISK SCORE CALCULATOR
class ModificationRiskCalculator:
    """Calculate risk score for modifications (1-10 scale)"""
    
    RISK_FACTORS = {
        'warranty_void': 3.0,
        'insurance_impact': 2.5,
        'installation_complexity': 2.0,
        'maintenance_cost': 1.5,
        'resale_impact': 1.0,
        'legal_compliance': 3.0
    }
    
    @staticmethod
    def calculate_modification_risk(modification_data, car_data, user_data):
        """Calculate overall risk score (1-10)"""
        risk_scores = []
        
        # 1. Warranty Risk
        warranty_risk = ModificationRiskCalculator._calculate_warranty_risk(
            modification_data['category'], 
            car_data.get('car_year', datetime.now().year)
        )
        risk_scores.append(warranty_risk * ModificationRiskCalculator.RISK_FACTORS['warranty_void'])
        
        # 2. Insurance Impact
        insurance_risk = ModificationRiskCalculator._calculate_insurance_risk(
            modification_data['category'], 
            modification_data.get('price', 0)
        )
        risk_scores.append(insurance_risk * ModificationRiskCalculator.RISK_FACTORS['insurance_impact'])
        
        # 3. Installation Complexity
        complexity_risk = ModificationRiskCalculator._calculate_complexity_risk(
            modification_data['category']
        )
        risk_scores.append(complexity_risk * ModificationRiskCalculator.RISK_FACTORS['installation_complexity'])
        
        # 4. Maintenance Cost Impact
        maintenance_risk = ModificationRiskCalculator._calculate_maintenance_risk(
            modification_data['category']
        )
        risk_scores.append(maintenance_risk * ModificationRiskCalculator.RISK_FACTORS['maintenance_cost'])
        
        # 5. Resale Value Impact
        resale_risk = ModificationRiskCalculator._calculate_resale_risk(
            modification_data['category'], 
            car_data.get('car_make', '')
        )
        risk_scores.append(resale_risk * ModificationRiskCalculator.RISK_FACTORS['resale_impact'])
        
        # 6. Legal Compliance
        legal_risk = ModificationRiskCalculator._calculate_legal_risk(
            modification_data['category'], 
            car_data.get('car_year', datetime.now().year)
        )
        risk_scores.append(legal_risk * ModificationRiskCalculator.RISK_FACTORS['legal_compliance'])
        
        # Calculate weighted average
        total_weight = sum(ModificationRiskCalculator.RISK_FACTORS.values())
        weighted_risk = sum(risk_scores) / total_weight
        
        # Normalize to 1-10 scale
        normalized_risk = min(max(weighted_risk * 2, 1), 10)
        
        return round(normalized_risk, 1)
    
    @staticmethod
    def _calculate_warranty_risk(mod_category, car_year):
        """Calculate warranty void risk (0-5 scale)"""
        warranty_risks = {
            'Performance': 4.5 if car_year < 3 else 3.0,
            'Technology': 2.0,
            'Safety': 1.0,
            'Comfort': 1.5,
            'Aesthetic': 0.5,
            'Color': 0.1
        }
        return warranty_risks.get(mod_category, 2.0)
    
    @staticmethod
    def _calculate_insurance_risk(mod_category, price):
        """Calculate insurance premium impact (0-5 scale)"""
        if price > 50000:
            risk = 4.0
        elif price > 20000:
            risk = 3.0
        elif price > 5000:
            risk = 2.0
        else:
            risk = 1.0
        
        # Category adjustments
        if mod_category == 'Performance':
            risk += 1.0
        elif mod_category == 'Safety':
            risk -= 0.5
        
        return min(max(risk, 0), 5)
    
    @staticmethod
    def _calculate_complexity_risk(mod_category):
        """Calculate installation complexity (0-5 scale)"""
        complexity = {
            'Performance': 4.0,
            'Technology': 3.5,
            'Safety': 3.0,
            'Comfort': 2.5,
            'Aesthetic': 2.0,
            'Color': 1.5
        }
        return complexity.get(mod_category, 2.5)
    
    @staticmethod
    def _calculate_maintenance_risk(mod_category):
        """Calculate maintenance cost impact (0-5 scale)"""
        maintenance = {
            'Performance': 3.5,
            'Technology': 3.0,
            'Safety': 2.0,
            'Comfort': 2.5,
            'Aesthetic': 1.5,
            'Color': 1.0
        }
        return maintenance.get(mod_category, 2.0)
    
    @staticmethod
    def _calculate_resale_risk(mod_category, car_make):
        """Calculate resale value impact (0-5 scale)"""
        # Premium brands benefit more from mods
        premium_brands = ['Mercedes', 'BMW', 'Audi', 'Porsche', 'Lexus']
        is_premium = any(brand.lower() in str(car_make).lower() for brand in premium_brands)
        
        resale_impact = {
            'Performance': 2.5 if is_premium else 3.5,
            'Technology': 2.0,
            'Safety': 1.0,
            'Comfort': 1.5,
            'Aesthetic': 3.0 if is_premium else 2.0,
            'Color': 4.0  # Color changes can significantly impact resale
        }
        return resale_impact.get(mod_category, 2.5)
    
    @staticmethod
    def _calculate_legal_risk(mod_category, car_year):
        """Calculate legal compliance risk (0-5 scale)"""
        legal_risks = {
            'Performance': 3.5 if car_year < 10 else 4.0,  # Older cars have more restrictions
            'Technology': 1.0,
            'Safety': 0.5,
            'Comfort': 1.0,
            'Aesthetic': 2.0,
            'Color': 3.0  # Color changes require RTO approval
        }
        return legal_risks.get(mod_category, 2.0)
    
    @staticmethod
    def get_risk_interpretation(risk_score):
        """Interpret the risk score"""
        if risk_score <= 3:
            return {
                "level": "Low Risk",
                "color": "#28a745",
                "description": "Safe modification with minimal impact",
                "recommendation": "Recommended for all users"
            }
        elif risk_score <= 6:
            return {
                "level": "Medium Risk",
                "color": "#ffc107",
                "description": "Moderate impact on warranty/insurance",
                "recommendation": "Consult with our experts before proceeding"
            }
        else:
            return {
                "level": "High Risk",
                "color": "#dc3545",
                "description": "Significant impact on warranty, insurance, and legality",
                "recommendation": "Professional consultation mandatory"
            }

# 3. CUSTOMER CLASSIFICATION SYSTEM
class CustomerClassifier:
    """Automatically classify customers into types"""
    
    CUSTOMER_TYPES = {
        0: {
            "name": "Performance Seeker",
            "description": "Focuses on speed, power, and handling improvements",
            "icon": "⚡",
            "color": "#dc3545",
            "preferred_categories": ["Performance", "Safety"],
            "avg_spend_range": "High (₹50,000+)",
            "typical_mods": ["Turbocharger", "ECU Remap", "Sports Suspension"]
        },
        1: {
            "name": "Daily Comfort",
            "description": "Prioritizes comfort, convenience, and reliability",
            "icon": "🛋️",
            "color": "#28a745",
            "preferred_categories": ["Comfort", "Technology"],
            "avg_spend_range": "Medium (₹20,000-₹50,000)",
            "typical_mods": ["Premium Seats", "Climate Control", "Audio System"]
        },
        2: {
            "name": "Luxury / Aesthetic",
            "description": "Focuses on looks, luxury features, and visual appeal",
            "icon": "💎",
            "color": "#6f42c1",
            "preferred_categories": ["Aesthetic", "Color", "Comfort"],
            "avg_spend_range": "High (₹50,000+)",
            "typical_mods": ["Custom Paint", "Body Kits", "Leather Interior"]
        }
    }
    
    def __init__(self):
        self.conn = get_db_connection()
        
    def extract_customer_features(self, customer_email):
        """Extract features for classification"""
        cursor = self.conn.cursor()
        
        features = {}
        
        # 1. Spending patterns
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT b.bill_id) as total_orders,
                SUM(b.total) as total_spent,
                AVG(b.total) as avg_order_value
            FROM bills b
            WHERE b.customer_email = ?
        """, (customer_email,))
        
        spending = cursor.fetchone()
        features['total_orders'] = spending['total_orders'] or 0
        features['total_spent'] = spending['total_spent'] or 0
        features['avg_order_value'] = spending['avg_order_value'] or 0
        
        # 2. Category preferences
        cursor.execute("""
            SELECT 
                bi.mod_category,
                COUNT(*) as mod_count,
                SUM(bi.total_price) as category_spent
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.bill_id
            WHERE b.customer_email = ?
            GROUP BY bi.mod_category
        """, (customer_email,))
        
        categories = cursor.fetchall()
        
        # Initialize category features
        all_categories = ['Performance', 'Aesthetic', 'Technology', 'Safety', 'Comfort', 'Color']
        for cat in all_categories:
            features[f'cat_{cat.lower()}_count'] = 0
            features[f'cat_{cat.lower()}_spent'] = 0
        
        # Fill category data
        for cat in categories:
            cat_name = cat['mod_category'].lower()
            features[f'cat_{cat_name}_count'] = cat['mod_count']
            features[f'cat_{cat_name}_spent'] = cat['category_spent']
        
        return features
    
    def classify_customer(self, customer_email):
        """Classify customer using rule-based system"""
        features = self.extract_customer_features(customer_email)
        
        # Rule-based classification
        performance_ratio = features.get('cat_performance_spent', 0) / max(features.get('total_spent', 1), 1)
        aesthetic_ratio = features.get('cat_aesthetic_spent', 0) / max(features.get('total_spent', 1), 1)
        comfort_ratio = features.get('cat_comfort_spent', 0) / max(features.get('total_spent', 1), 1)
        
        # Determine dominant preference
        if performance_ratio > 0.4:
            return self.CUSTOMER_TYPES[0]  # Performance Seeker
        elif aesthetic_ratio > 0.3:
            return self.CUSTOMER_TYPES[2]  # Luxury/Aesthetic
        else:
            return self.CUSTOMER_TYPES[1]  # Daily Comfort
    
    def get_recommendations_for_type(self, customer_type_idx):
        """Get modification recommendations based on customer type"""
        recommendations = {
            0: {  # Performance Seeker
                "must_have": ["Stage 2 ECU Remap", "Performance Exhaust", "Sports Suspension"],
                "recommended": ["Turbocharger Kit", "Advanced Brake System", "Lightweight Wheels"],
                "budget_friendly": ["Air Intake System", "Performance Chip", "Strut Bar"]
            },
            1: {  # Daily Comfort
                "must_have": ["Premium Leather Seats", "Dual Zone Climate Control", "Premium Sound System"],
                "recommended": ["Heated Seats", "Noise Insulation", "Adaptive Cruise Control"],
                "budget_friendly": ["Seat Covers", "Steering Wheel Cover", "Car Organizer"]
            },
            2: {  # Luxury / Aesthetic
                "must_have": ["Ceramic Coating", "Custom Paint Job", "LED Headlight Kit"],
                "recommended": ["Body Kit", "Chrome Accessories", "Ambient Lighting"],
                "budget_friendly": ["Vinyl Wrap", "Alloy Wheel Covers", "Window Tinting"]
            }
        }
        
        return recommendations.get(customer_type_idx, recommendations[1])
    
    def __del__(self):
        self.conn.close()

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
                        add_notification(f"Welcome back, {customer['name']}!", "success")
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
                        add_notification("Registration successful! Welcome to our studio!", "success")
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
            
            if st.button("Add Car", type="primary"):
                if not car_model:
                    st.error("Car Model is required")
                else:
                    cursor.execute("""
                        INSERT INTO cars (customer_email, car_model, car_make, car_year, car_color) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (st.session_state.user_email, car_model, car_make, car_year, car_color))
                    conn.commit()
                    add_notification(f"Car '{car_model}' added successfully!", "success")
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
                    add_notification(f"Car '{new_car_model}' added successfully!", "success")
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
                            add_notification(f"Removed {mod['name']} from cart", "info")
                            st.rerun()
                    else:
                        if st.button(f"✅ Select", key=f"select_{mod['mod_id']}"):
                            st.session_state.selected_mods.append(mod)
                            add_notification(f"Added {mod['name']} to cart", "success")
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
                        add_notification(f"Removed color selection", "info")
                        st.rerun()
                else:
                    if st.button(f"🎨 Select Color", key=f"select_color_{color['mod_id']}"):
                        st.session_state.selected_color = color
                        add_notification(f"Selected {color['name']} color", "success")
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
                
                add_notification("Purchase completed successfully!", "success")
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
    
    # Price comparison using Streamlit charts
    if categories:
        st.subheader("📊 Price Statistics by Category")
        
        # Prepare data for display
        price_data = []
        for category, mods_list in categories.items():
            prices = [mod['price'] for mod in mods_list]
            price_data.append({
                'Category': category,
                'Min Price': f"₹{min(prices):,.2f}",
                'Max Price': f"₹{max(prices):,.2f}",
                'Avg Price': f"₹{sum(prices)/len(prices):,.2f}",
                'Count': len(prices)
            })
        
        df = pd.DataFrame(price_data)
        st.dataframe(df, use_container_width=True)

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
                    add_notification("Appointment scheduled successfully!", "success")
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
            
            # Display data table
            st.dataframe(df_monthly, use_container_width=True)
            
            # Simple charts using Streamlit's built-in charts
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Monthly Spending")
                st.bar_chart(df_monthly.set_index('Month')['Total_Spent'])
            with col2:
                st.subheader("Average Bill Trend")
                st.line_chart(df_monthly.set_index('Month')['Avg_Bill'])
            
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
            
            # Display data
            st.dataframe(df_mods, use_container_width=True, hide_index=True)
            
            # Simple visualization
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Spending by Category")
                category_summary = df_mods.groupby('Category')['Total_Spent'].sum()
                st.bar_chart(category_summary)
            with col2:
                st.subheader("Top Modifications")
                top_mods = df_mods.nlargest(5, 'Total_Spent')
                st.bar_chart(top_mods.set_index('Modification')['Total_Spent'])
    
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

# AI Recommendations Page
def ai_recommendations_page():
    if not st.session_state.user_email:
        st.warning("Please login to get AI recommendations")
        return
    
    st.title("🤖 AI-Powered Modification Recommendations")
    
    # Initialize AI engine
    ai_engine = AIRecommendationEngine()
    
    # Get recommendations
    recommendations = ai_engine.get_personalized_recommendations(st.session_state.user_email, limit=6)
    
    if recommendations:
        st.markdown(f"### Personalized Recommendations for {st.session_state.user_name}")
        st.caption("Based on your purchase history, preferences, and car details")
        
        # Display recommendations in a grid
        cols = st.columns(2)
        
        for idx, rec in enumerate(recommendations):
            with cols[idx % 2]:
                # Get risk score
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT car_model, car_make, car_year FROM cars WHERE customer_email = ? LIMIT 1", 
                             (st.session_state.user_email,))
                car_data = cursor.fetchone() or {}
                conn.close()
                
                risk_score = ModificationRiskCalculator.calculate_modification_risk(
                    {"category": rec['category'], "price": rec['price']},
                    car_data,
                    {"email": st.session_state.user_email}
                )
                risk_info = ModificationRiskCalculator.get_risk_interpretation(risk_score)
                
                # Determine risk class
                if risk_score <= 3:
                    risk_class = "risk-low"
                elif risk_score <= 6:
                    risk_class = "risk-medium"
                else:
                    risk_class = "risk-high"
                
                # Display card
                st.markdown(f"""
                <div class="mod-card" style="border-left: 4px solid {risk_info['color']};">
                    <h4>{rec['name']}</h4>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="price-tag">₹{rec['price']:,.2f}</span>
                        <span style="background-color: {risk_info['color']}20; color: {risk_info['color']}; 
                              padding: 2px 8px; border-radius: 12px; font-size: 0.8em;">
                            Risk: {risk_score}/10
                        </span>
                    </div>
                    <p><small>📊 AI Match: {rec['ai_score']}%</small></p>
                    <p><small>🎯 {rec['reason']}</small></p>
                    <p><small>⚠️ {risk_info['description']}</small></p>
                </div>
                """, unsafe_allow_html=True)
                
                # Add to cart button
                if st.button(f"➕ Add to Cart", key=f"ai_add_{rec['mod_id']}", use_container_width=True):
                    # Add to selected mods
                    mod_info = {
                        'mod_id': rec['mod_id'],
                        'name': rec['name'],
                        'price': rec['price'],
                        'category': rec['category']
                    }
                    if mod_info not in st.session_state.selected_mods:
                        st.session_state.selected_mods.append(mod_info)
                        add_notification(f"Added {rec['name']} to cart", "success")
                        st.success(f"Added {rec['name']} to cart!")
                        st.rerun()
    else:
        st.info("We need more data about your preferences. Make your first purchase to get personalized recommendations!")
        
        # Show popular modifications
        st.markdown("### Popular Among Customers")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.mod_id, m.name, m.price, m.category, m.description
            FROM modifications m
            WHERE m.is_active = 1
            ORDER BY m.price DESC
            LIMIT 6
        """)
        
        popular_mods = cursor.fetchall()
        conn.close()
        
        cols = st.columns(2)
        for idx, mod in enumerate(popular_mods):
            with cols[idx % 2]:
                st.markdown(f"""
                <div class="mod-card">
                    <h4>{mod['name']}</h4>
                    <p class="price-tag">₹{mod['price']:,.2f}</p>
                    <p><small>{mod['description'] or 'No description'}</small></p>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"➕ Add", key=f"pop_add_{mod['mod_id']}", use_container_width=True):
                    mod_info = {
                        'mod_id': mod['mod_id'],
                        'name': mod['name'],
                        'price': mod['price'],
                        'category': mod['category']
                    }
                    if mod_info not in st.session_state.selected_mods:
                        st.session_state.selected_mods.append(mod_info)
                        add_notification(f"Added {mod['name']} to cart", "success")
                        st.success(f"Added {mod['name']} to cart!")
                        st.rerun()

# Risk Analysis Page
def risk_analysis_page():
    if not st.session_state.user_email:
        st.warning("Please login to view risk analysis")
        return
    
    st.title("⚠️ Modification Risk Analysis")
    
    # Get customer's selected modifications
    if not st.session_state.selected_mods:
        st.info("Please select some modifications first to analyze their risk.")
        if st.button("Go to Build Page"):
            st.session_state.current_page = "build"
            st.rerun()
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get car information
    cursor.execute("SELECT car_model, car_make, car_year FROM cars WHERE customer_email = ? LIMIT 1", 
                  (st.session_state.user_email,))
    car_data = cursor.fetchone() or {}
    
    # Get customer information
    cursor.execute("SELECT total_visits, total_spent FROM customers WHERE email = ?", 
                  (st.session_state.user_email,))
    customer_data = cursor.fetchone() or {}
    
    st.markdown(f"### Risk Analysis for {car_data.get('car_model', 'Your Car')}")
    
    # Overall risk assessment
    st.subheader("📊 Overall Risk Assessment")
    
    total_risk = 0
    high_risk_count = 0
    risk_details = []
    
    for mod in st.session_state.selected_mods:
        mod_data = {
            'category': mod['category'],
            'price': mod['price'],
            'name': mod['name']
        }
        
        risk_score = ModificationRiskCalculator.calculate_modification_risk(
            mod_data, car_data, customer_data
        )
        
        risk_info = ModificationRiskCalculator.get_risk_interpretation(risk_score)
        
        risk_details.append({
            'modification': mod['name'],
            'category': mod['category'],
            'risk_score': risk_score,
            'risk_level': risk_info['level'],
            'color': risk_info['color'],
            'details': risk_info['description']
        })
        
        total_risk += risk_score
        if risk_score > 6:
            high_risk_count += 1
    
    avg_risk = total_risk / len(st.session_state.selected_mods) if st.session_state.selected_mods else 0
    
    # Overall risk metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        overall_risk_info = ModificationRiskCalculator.get_risk_interpretation(avg_risk)
        st.metric("Average Risk", f"{avg_risk:.1f}/10", 
                 delta=overall_risk_info['level'], delta_color="inverse")
    with col2:
        st.metric("High Risk Mods", high_risk_count)
    with col3:
        st.metric("Total Mods", len(st.session_state.selected_mods))
    
    # Risk breakdown
    st.subheader("📈 Risk Breakdown by Modification")
    
    # Create DataFrame for display
    risk_df = pd.DataFrame(risk_details)
    
    # Display risk table
    st.dataframe(risk_df[['modification', 'category', 'risk_score', 'risk_level']], 
                 use_container_width=True)
    
    # Visual risk representation
    st.subheader("🎯 Risk Distribution")
    
    # Create simple bar chart using Streamlit
    if not risk_df.empty:
        chart_data = risk_df.set_index('modification')['risk_score']
        st.bar_chart(chart_data)
    
    # Detailed risk analysis
    st.subheader("🔍 Detailed Risk Analysis")
    
    for detail in risk_details:
        with st.expander(f"{detail['modification']} - Risk: {detail['risk_score']}/10 ({detail['risk_level']})"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Category:** {detail['category']}")
                st.markdown(f"**Risk Level:** <span style='color:{detail['color']};font-weight:bold'>{detail['risk_level']}</span>", 
                           unsafe_allow_html=True)
                st.markdown(f"**Score:** {detail['risk_score']}/10")
            with col2:
                # Show individual risk factors
                st.markdown("**Risk Factors:**")
                
                # Calculate individual factors
                warranty_risk = ModificationRiskCalculator._calculate_warranty_risk(
                    detail['category'], car_data.get('car_year', datetime.now().year)
                )
                
                insurance_risk = ModificationRiskCalculator._calculate_insurance_risk(
                    detail['category'], next((m['price'] for m in st.session_state.selected_mods if m['name'] == detail['modification']), 0)
                )
                
                st.write(f"• Warranty Impact: {warranty_risk:.1f}/5")
                st.write(f"• Insurance Impact: {insurance_risk:.1f}/5")
                st.write(f"• Legal Compliance: {ModificationRiskCalculator._calculate_legal_risk(detail['category'], car_data.get('car_year', datetime.now().year)):.1f}/5")
            
            st.markdown(f"**Recommendation:** {ModificationRiskCalculator.get_risk_interpretation(detail['risk_score'])['recommendation']}")
    
    # Risk mitigation suggestions
    st.subheader("🛡️ Risk Mitigation Suggestions")
    
    if high_risk_count > 0:
        st.warning(f"You have {high_risk_count} high-risk modifications selected.")
        
        suggestions = []
        
        if any(d['risk_score'] > 8 for d in risk_details):
            suggestions.append("⚠️ Consider removing modifications with risk score > 8")
        
        if any(d['category'] == 'Performance' and d['risk_score'] > 6 for d in risk_details):
            suggestions.append("⚡ High-performance mods may void warranty. Get written approval from dealership.")
        
        if any(d['category'] == 'Color' for d in risk_details):
            suggestions.append("🎨 Color changes require RTO approval. We can help with documentation.")
        
        for suggestion in suggestions:
            st.info(suggestion)
    
    # Insurance impact estimate
    st.subheader("💰 Estimated Insurance Impact")
    
    total_mod_value = sum(mod['price'] for mod in st.session_state.selected_mods)
    insurance_increase = total_mod_value * 0.15  # 15% increase estimate
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Modification Value", f"₹{total_mod_value:,.2f}")
    with col2:
        st.metric("Estimated Premium Increase", f"₹{insurance_increase:,.2f}/year")
    
    st.caption("Note: Actual premium may vary based on insurance provider and policy terms.")
    
    conn.close()

# Customer Classification Page
def customer_classification_page():
    if not st.session_state.user_email:
        st.warning("Please login to view customer classification")
        return
    
    st.title("👤 Customer Classification & Insights")
    
    # Initialize classifier
    classifier = CustomerClassifier()
    
    # Classify customer
    with st.spinner("Analyzing your profile..."):
        customer_type = classifier.classify_customer(st.session_state.user_email)
    
    # Display classification result
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown(f"""
        <div style="text-align: center; padding: 2rem; background: {customer_type['color']}20; 
             border-radius: 10px; border: 2px solid {customer_type['color']};">
            <h1 style="font-size: 4rem; margin: 0;">{customer_type['icon']}</h1>
            <h3>{customer_type['name']}</h3>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"### {customer_type['name']}")
        st.write(customer_type['description'])
        
        st.markdown("**Preferred Categories:**")
        for cat in customer_type['preferred_categories']:
            st.write(f"• {cat}")
        
        st.markdown(f"**Average Spend:** {customer_type['avg_spend_range']}")
        
        st.markdown("**Typical Modifications:**")
        for mod in customer_type['typical_mods'][:3]:
            st.write(f"• {mod}")
    
    st.markdown("---")
    
    # Get customer type index
    customer_type_idx = next(
        (key for key, value in CustomerClassifier.CUSTOMER_TYPES.items() 
         if value['name'] == customer_type['name']),
        1
    )
    
    # Get recommendations for this customer type
    recommendations = classifier.get_recommendations_for_type(customer_type_idx)
    
    st.subheader("🎯 Recommended Modifications For You")
    
    tabs = st.tabs(["Must Have", "Recommended", "Budget Friendly"])
    
    with tabs[0]:
        for mod in recommendations['must_have']:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"✅ {mod}")
            with col2:
                if st.button("🔍 Find", key=f"must_{mod}"):
                    add_notification(f"Searching for {mod}", "info")
    
    with tabs[1]:
        for mod in recommendations['recommended']:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"⭐ {mod}")
            with col2:
                if st.button("🔍 Find", key=f"rec_{mod}"):
                    add_notification(f"Searching for {mod}", "info")
    
    with tabs[2]:
        for mod in recommendations['budget_friendly']:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"💰 {mod}")
            with col2:
                if st.button("🔍 Find", key=f"budget_{mod}"):
                    add_notification(f"Searching for {mod}", "info")
    
    st.markdown("---")
    
    # Customer insights
    st.subheader("📊 Your Modification Profile")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get spending by category
    cursor.execute("""
        SELECT 
            bi.mod_category,
            COUNT(*) as mod_count,
            SUM(bi.total_price) as total_spent,
            AVG(bi.price) as avg_price
        FROM bill_items bi
        JOIN bills b ON bi.bill_id = b.bill_id
        WHERE b.customer_email = ?
        GROUP BY bi.mod_category
        ORDER BY total_spent DESC
    """, (st.session_state.user_email,))
    
    category_data = cursor.fetchall()
    
    if category_data:
        # Create summary table
        summary_data = []
        for row in category_data:
            summary_data.append({
                'Category': row['mod_category'],
                'Modifications': row['mod_count'],
                'Total Spent': f"₹{row['total_spent']:,.2f}",
                'Average Price': f"₹{row['avg_price']:,.2f}"
            })
        
        df_summary = pd.DataFrame(summary_data)
        st.dataframe(df_summary, use_container_width=True)
        
        # Simple chart
        if len(summary_data) > 0:
            st.subheader("📈 Spending Distribution")
            chart_data = pd.DataFrame({
                'Category': [item['Category'] for item in summary_data],
                'Spent': [float(item['Total Spent'].replace('₹', '').replace(',', '')) 
                         for item in summary_data]
            })
            st.bar_chart(chart_data.set_index('Category')['Spent'])
        
        # Spending statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            total_mods = sum(row['mod_count'] for row in category_data)
            st.metric("Total Modifications", total_mods)
        with col2:
            total_spent = sum(row['total_spent'] for row in category_data)
            st.metric("Total Spent on Mods", f"₹{total_spent:,.2f}")
        with col3:
            avg_per_mod = total_spent / total_mods if total_mods > 0 else 0
            st.metric("Average per Mod", f"₹{avg_per_mod:,.2f}")
    else:
        st.info("No modification history yet. Start building to see your profile!")
    
    conn.close()

# 3D Car Preview Page
def car_3d_preview_page():
    if not st.session_state.user_email:
        st.warning("Please login to use 3D Preview")
        return
    
    st.title("🎮 3D Car Customization Preview")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### Visualize Your Modifications")
        
        # Car model selection
        car_models = ["Sedan", "SUV", "Sports Car", "Hatchback", "Pickup Truck"]
        selected_model = st.selectbox("Select Car Model", car_models)
        
        # Color picker
        selected_color = st.color_picker("Choose Car Color", "#FF0000")
        
        # Modification visualization
        st.markdown("### Applied Modifications")
        if st.session_state.selected_mods:
            for mod in st.session_state.selected_mods:
                st.write(f"✅ {mod['name']}")
        
        # 3D visualization placeholder
        st.markdown("""
        <div class="car-3d-view" style="height: 400px; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #667eea20 0%, #764ba220 100%);">
            <div style="text-align: center;">
                <h3>🚗 3D Preview</h3>
                <p>Selected Model: <strong>{}</strong></p>
                <div style="width: 100px; height: 100px; background-color: {}; margin: 20px auto; border-radius: 10px;"></div>
                <p>Selected Color</p>
                <p>Modifications Applied: <strong>{}</strong></p>
            </div>
        </div>
        """.format(selected_model, selected_color, len(st.session_state.selected_mods)), unsafe_allow_html=True)
    
    with col2:
        st.markdown("### Modification Effects")
        
        # Performance metrics
        if st.session_state.selected_mods:
            performance_boost = sum(1 for mod in st.session_state.selected_mods if mod['category'] == 'Performance') * 15
            aesthetics_boost = sum(1 for mod in st.session_state.selected_mods if mod['category'] == 'Aesthetic') * 10
            tech_boost = sum(1 for mod in st.session_state.selected_mods if mod['category'] == 'Technology') * 12
            
            st.metric("🚀 Performance Boost", f"+{performance_boost}%")
            st.metric("🎨 Aesthetics Boost", f"+{aesthetics_boost}%")
            st.metric("⚡ Tech Boost", f"+{tech_boost}%")
        
        # Estimated value increase
        if st.session_state.selected_mods:
            total_investment = sum(mod['price'] for mod in st.session_state.selected_mods)
            value_increase = total_investment * 0.3  # 30% value increase
            st.metric("📈 Estimated Value Increase", f"₹{value_increase:,.2f}")

# Cart Page
def show_cart_page():
    st.title("🛒 Your Cart")
    
    if not st.session_state.selected_mods and not st.session_state.selected_color:
        st.info("Your cart is empty. Start adding modifications!")
        if st.button("Go to Build Page", type="primary"):
            st.session_state.view_cart = False
            st.session_state.current_page = "build"
            st.rerun()
        return
    
    # Show selected items
    st.subheader("Selected Items")
    
    total_price = 0
    
    # Modifications
    if st.session_state.selected_mods:
        st.markdown("### 🔧 Modifications")
        for mod in st.session_state.selected_mods:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"• {mod['name']}")
            with col2:
                st.write(f"₹{mod['price']:,.2f}")
            with col3:
                if st.button("❌", key=f"remove_mod_{mod['mod_id']}"):
                    st.session_state.selected_mods.remove(mod)
                    add_notification(f"Removed {mod['name']} from cart", "info")
                    st.rerun()
            total_price += mod['price']
    
    # Color
    if st.session_state.selected_color:
        st.markdown("### 🎨 Color")
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.write(f"• {st.session_state.selected_color['name']}")
        with col2:
            st.write(f"₹{st.session_state.selected_color['price']:,.2f}")
        with col3:
            if st.button("❌", key="remove_color"):
                st.session_state.selected_color = None
                add_notification(f"Removed color selection", "info")
                st.rerun()
        total_price += st.session_state.selected_color['price']
    
    st.markdown("---")
    
    # Price summary
    totals = calculate_totals(st.session_state.selected_mods, 
                             st.session_state.selected_color,
                             st.session_state.user_email)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 💰 Price Summary")
        st.write(f"**Subtotal:** ₹{totals['subtotal']:,.2f}")
        if totals['discount_percent'] > 0:
            st.write(f"**Discount ({totals['discount_percent']}%):** -₹{totals['discount_amount']:,.2f}")
            st.write(f"**After Discount:** ₹{totals['subtotal_after_discount']:,.2f}")
        st.write(f"**GST (18%):** ₹{totals['gst']:,.2f}")
        st.markdown(f"### **Total:** ₹{totals['total']:,.2f}")
    
    with col2:
        st.markdown("### ⚡ Quick Actions")
        if st.button("🔄 Update Cart", use_container_width=True):
            st.rerun()
        if st.button("📝 Continue Building", use_container_width=True):
            st.session_state.view_cart = False
            st.session_state.current_page = "build"
            st.rerun()
        if st.button("⚠️ Check Risk Analysis", use_container_width=True):
            st.session_state.view_cart = False
            st.session_state.current_page = "risk_analysis"
            st.rerun()
        if st.button("💳 Proceed to Checkout", type="primary", use_container_width=True):
            if st.session_state.user_email:
                st.session_state.view_cart = False
                st.session_state.current_page = "build"  # This will show payment section
                st.rerun()
            else:
                st.warning("Please login to checkout")
                st.session_state.current_page = "auth"
                st.rerun()

# Settings Page
def settings_page():
    st.title("⚙️ Settings")
    
    if not st.session_state.user_email:
        st.warning("Please login to access settings")
        return
    
    tab1, tab2, tab3 = st.tabs(["Account", "Preferences", "Notifications"])
    
    with tab1:
        st.subheader("Account Settings")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE email = ?", (st.session_state.user_email,))
        customer = cursor.fetchone()
        
        if customer:
            with st.form("update_account"):
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input("Full Name", value=customer['name'])
                    email = st.text_input("Email", value=customer['email'], disabled=True)
                    phone = st.text_input("Phone", value=customer['phone'] or "")
                with col2:
                    address = st.text_area("Address", value=customer['address'] or "")
                    city = st.text_input("City", value=customer['city'] or "")
                    state = st.text_input("State", value=customer['state'] or "")
                    pincode = st.text_input("Pincode", value=customer['pincode'] or "")
                
                if st.form_submit_button("Update Profile"):
                    cursor.execute("""
                        UPDATE customers 
                        SET name = ?, phone = ?, address = ?, city = ?, state = ?, pincode = ?
                        WHERE email = ?
                    """, (name, phone, address, city, state, pincode, st.session_state.user_email))
                    conn.commit()
                    st.session_state.user_name = name
                    add_notification("Profile updated successfully!", "success")
                    st.success("Profile updated!")
        
        conn.close()
    
    with tab2:
        st.subheader("Preferences")
        
        col1, col2 = st.columns(2)
        with col1:
            dark_mode = st.checkbox("Dark Mode", value=st.session_state.dark_mode)
            if dark_mode != st.session_state.dark_mode:
                st.session_state.dark_mode = dark_mode
                add_notification("Theme preference updated", "info")
            
            email_notifications = st.checkbox("Email Notifications", value=True)
            sms_notifications = st.checkbox("SMS Notifications", value=False)
        
        with col2:
            currency = st.selectbox("Currency", ["₹ INR", "$ USD", "€ EUR", "£ GBP"])
            language = st.selectbox("Language", ["English", "Hindi", "Spanish", "French"])
            
            if st.button("Save Preferences"):
                add_notification("Preferences saved!", "success")
                st.success("Preferences saved!")
    
    with tab3:
        st.subheader("Notification Settings")
        
        st.write("Configure what notifications you want to receive:")
        
        notification_types = {
            "Order Updates": True,
            "Promotional Offers": True,
            "Appointment Reminders": True,
            "New Features": False,
            "Security Alerts": True
        }
        
        for notif_type, default_value in notification_types.items():
            st.checkbox(notif_type, value=default_value)
        
        if st.button("Update Notification Settings"):
            add_notification("Notification settings updated", "success")
            st.success("Notification settings updated!")

# Main app router
def main():
    show_header()
    show_sidebar()
    
    # Check for cart view first
    if st.session_state.view_cart:
        show_cart_page()
        return
    
    # Map page names to functions
    page_functions = {
        "home": home_page,
        "auth": auth_page,
        "build": build_page,
        "pricing": pricing_page,
        "profile": profile_page,
        "appointments": appointments_page,
        "reports": reports_page,
        "export": export_page,
        "preview": car_3d_preview_page,
        "ai_recommend": ai_recommendations_page,
        "risk_analysis": risk_analysis_page,
        "customer_class": customer_classification_page,
        "settings": settings_page
    }
    
    # Get current page from session state
    current_page = st.session_state.current_page
    
    if current_page in page_functions:
        page_functions[current_page]()
    else:
        home_page()

# Update database tables
def update_database_tables():
    """Update database with new tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create wallet transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wallet_transactions (
        transaction_id TEXT PRIMARY KEY,
        customer_email TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_method TEXT NOT NULL,
        description TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_email) REFERENCES customers(email)
    )
    """)
    
    # Create community posts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS community_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        category TEXT NOT NULL,
        likes INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_email) REFERENCES customers(email)
    )
    """)
    
    conn.commit()
    conn.close()

# Run database update on startup
update_database_tables()

if __name__ == "__main__":
    main()
