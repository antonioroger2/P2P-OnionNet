import streamlit as st
import time
from ui.pages_chat import render_chat
from ui.pages_torrent import render_torrent
from ui.pages_http_proxy import render_proxy

def render_dashboard(node):
    with st.sidebar:
        st.header("OnionNet Status")
        st.markdown(f"**My IP:** `{node.get_local_ip()}`")
        st.markdown(f"**My Port:** `{node.port}`")

        status_color = "green" if len(node.peers) > 0 else "orange"
        st.markdown(f"**Connection:** :{status_color}[Online]")

        with st.expander("Add Peer Manually"):
            with st.form("manual_peer"):
                target_ip = st.text_input("IP Address", value="192.168.1.")
                target_port = st.text_input("Port", value="6000")
                if st.form_submit_button("Connect"):
                    node.discovery.manual_connect(target_ip, target_port)
                    st.success(f"Ping sent to {target_ip}:{target_port}")

        st.subheader(f"Peers ({len(node.peers)})")
        for pid in node.peers:
            st.code(pid)

        if st.button("Refresh Network"):
            st.rerun()

    tab1, tab2, tab3 = st.tabs(["💬 Encrypted Chat", "🐝 Artifact Swarm", "🌐 Onion Proxy"])

    with tab1:
        render_chat(node)
    with tab2:
        render_torrent(node)
    with tab3:
        render_proxy(node)

    time.sleep(1)
    st.rerun()