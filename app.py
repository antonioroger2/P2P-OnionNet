import streamlit as st
import os
from core.overlay import OnionNode
from ui.dashboard import render_dashboard

os.makedirs("data/received", exist_ok=True)
os.makedirs("data/shared", exist_ok=True)
os.makedirs("data/torrents", exist_ok=True)

st.set_page_config(
    page_title="OnionNet P2P",
    page_icon="🧅",
    layout="wide",
    initial_sidebar_state="expanded"
)

if 'node' not in st.session_state:
    st.session_state.node = OnionNode(bind_ip='0.0.0.0')

render_dashboard(st.session_state.node)