import streamlit as st
import time
from ui.pages_chat import render_chat
from ui.pages_torrent import render_torrent
from ui.pages_http_proxy import render_proxy

def render_dashboard(node):
    # Sidebar: Network Stats
    with st.sidebar:
        st.header("OnionNet Status")
        st.markdown(f"**My Port:** `{node.port}`")

        status_color = "green" if len(node.peers) > 0 else "orange"
        st.markdown(f"**Connection:** :{status_color}[Online]")

        st.subheader(f"Peers ({len(node.peers)})")
        for pid in node.peers:
            st.code(pid)

        if st.button("Refresh Network"):
            st.rerun()

    # Main Tabs
    tab1, tab2, tab3 = st.tabs(["💬 Encrypted Chat", "🐝 Artifact Swarm", "🌐 Onion Proxy"])

    with tab1:
        render_chat(node)
    with tab2:
        render_torrent(node)
    with tab3:
        render_proxy(node)

    # Auto-refresh mechanism (Polling)
    time.sleep(1)
    st.rerun()
