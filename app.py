import streamlit as st
import os
from core.overlay import OnionNode
from ui.dashboard import render_dashboard

# Ensure data directories exist
os.makedirs("data/received", exist_ok=True)
os.makedirs("data/shared", exist_ok=True)
os.makedirs("data/torrents", exist_ok=True)

# Page Config
st.set_page_config(
    page_title="OnionNet P2P",
    page_icon="🧅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Core Backend (Singleton Pattern)
if 'node' not in st.session_state:
    # This starts the socket listeners and discovery threads
    st.session_state.node = OnionNode()

# Render the UI
render_dashboard(st.session_state.node)
