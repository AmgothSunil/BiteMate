"""
Streamlit Frontend for BiteMate - AI Meal Planner
"""
import streamlit as st
import requests
import uuid
from datetime import datetime

# Page config
st.set_page_config(
    page_title="BiteMate - AI Meal Planner",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: #FF6B6B;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .agent-output {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #FF6B6B;
        margin-bottom: 1rem;
    }
    .stButton>button {
        background-color: #FF6B6B;
        color: white;
        font-weight: bold;
        border-radius: 5px;
        padding: 0.5rem 2rem;
        border: none;
    }
    .stButton>button:hover {
        background-color: #FF5252;
    }
</style>
""", unsafe_allow_html=True)

# API Configuration
API_URL = "http://localhost:8050"

# User ID & Session Management

def get_or_create_user_id():
    """Get persistent user ID from URL params or create new UUID."""
    query_params = st.query_params
    
    if 'user_id' in query_params:
        return query_params['user_id']
    
    # Generate new UUID-based user ID
    new_user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    # Store in URL for persistence across browser sessions
    st.query_params['user_id'] = new_user_id
    
    return new_user_id

def create_new_session():
    """Create a new session ID for a fresh conversation."""
    st.session_state.session_id = f"session_{int(datetime.now().timestamp())}"
    st.session_state.history = []

# Initialize session state
if 'user_id' not in st.session_state:
    st.session_state.user_id = get_or_create_user_id()

if 'session_id' not in st.session_state:
    st.session_state.session_id = f"session_{int(datetime.now().timestamp())}"

if 'history' not in st.session_state:
    st.session_state.history = []


def call_api(user_input: str):
    """Call the FastAPI backend."""
    try:
        response = requests.post(
            f"{API_URL}/api/meal-plan",
            json={
                "user_id": st.session_state.user_id,
                "session_id": st.session_state.session_id,
                "user_input": user_input
            },
            timeout=180  # 3 minutes timeout for full agent chain
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure FastAPI is running on port 8000.")
        st.code("Run: uv run python api.py", language="bash")
        return None
    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out. The AI is taking longer than expected.")
        return None
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        return None


# Header
st.markdown('<div class="main-header">🍽️ BiteMate</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Your AI-Powered Personalized Meal Planning Assistant</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("👤 User Info")
    st.info(f"**User ID**: `{st.session_state.user_id[:16]}...`")
    st.caption(f"**Session**: `{st.session_state.session_id[-10:]}`")
    
    st.divider()
    
    # New Chat Button
    if st.button("🆕 New Chat", use_container_width=True, type="primary"):
        create_new_session()
        st.success("✅ New chat session started!")
        st.rerun()
    
    st.divider()
    
    st.header("ℹ️ How to Use")
    st.markdown("""
    1. **Enter your request** in the text box
    2. Include profile info if first time:
       - Age, weight, height
       - Health conditions
       - Diet preferences
    3. **Click Generate** to get meal plan
    4. View your personalized results!
    
    **What you'll get:**
    - Profile extraction & storage
    - Nutritional calculations
    - Recipe recommendations
    - Meal preparation instructions
    """)
    
    st.divider()
    
    if st.button("🗑️ Clear History", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# Main content
st.header("💬 What would you like to eat?")

# Example inputs
with st.expander("📝 Example Inputs"):
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🥗 Quick Request"):
            st.session_state.example_text = "I want healthy lunch recipes that are low carb and spicy"
    with col2:
        if st.button("👤 With Profile"):
            st.session_state.example_text = "I'm a 35-year-old male,68kg, 175cm tall. I have pre-diabetes and I'm trying to eat low carb. I want a spicy lunch."

# Text input
user_input = st.text_area(
    "Enter your request:",
    value=st.session_state.get('example_text', ''),
    height=150,
    placeholder="Example: Find me the best recipe for lunch",
    help="Include your profile info (age, weight, health conditions) along with your meal request"
)

# Generate button
if st.button("🎯 Generate Meal Plan", type="primary"):
    if not user_input.strip():
        st.warning("⚠️ Please enter your request first!")
    else:
        with st.spinner("🤖 AI Agents are working on your personalized meal plan..."):
            result = call_api(user_input)
            
            if result:
                # Add to history
                st.session_state.history.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "input": user_input,
                    "result": result
                })
                
                # Display results
                st.success("✅ Meal plan generated successfully!")
                
                # Session info
                with st.expander("📊 Session Info", expanded=False):
                    st.text(f"Session ID: {result.get('session_id', 'N/A')}")
                    st.text(f"User ID: {result.get('user_id', 'N/A')}")
                    st.text(f"Status: {result.get('status', 'N/A')}")
                
                # Display agent output
                st.header("🤖 Agent Response")
                
                agent_response = result.get('response', 'No response')
                
                
                # Also display as markdown for better rendering
                st.divider()
                st.subheader("📋 Detailed Output")
                st.markdown(agent_response)

# Display history
if st.session_state.history:
    st.divider()
    st.header("📜 Chat History")
    
    for idx, item in enumerate(reversed(st.session_state.history)):
        with st.expander(f"💬 {item['timestamp']} - Request #{len(st.session_state.history) - idx}"):
            st.markdown(f"**Your Input:**\n{item['input']}")
            st.divider()
            st.markdown(f"**Response:**\n{item['result'].get('response', 'No response')}")
