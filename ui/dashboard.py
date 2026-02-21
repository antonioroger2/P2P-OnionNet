import streamlit as st
import time
from ui.pages_chat import render_chat
from ui.pages_torrent import render_torrent
from ui.pages_http_proxy import render_proxy

def render_dashboard(node):
    # Initialize session state for manual connection fields if not present
    if "target_ip" not in st.session_state:
        st.session_state.target_ip = ""
    if "target_port" not in st.session_state:
        st.session_state.target_port = ""

    with st.sidebar:
        st.header("OnionNet Status")
        st.markdown(f"**My IP:** `{node.get_local_ip()}`")
        st.markdown(f"**Discovery Port (UDP):** `{node.discovery.discovery_port}`") 
        st.markdown(f"**Data Port (TCP):** `{node.port}`")

        status_color = "green" if len(node.peers) > 0 else "orange"
        st.markdown(f"**Connection:** :{status_color}[Online]")

        with st.expander("Add Peer Manually", expanded=True):
            with st.form("manual_peer"):
                st.caption("Ask your friend for their IP and UDP Port.")
                # Use session state for the values
                target_ip = st.text_input("Friend's IP", value=st.session_state.target_ip)
                target_port = st.text_input("Friend's Discovery Port (UDP)", value=st.session_state.target_port)
                
                if st.form_submit_button("Connect"):
                    if target_ip and target_port:
                        node.discovery.manual_connect(target_ip, target_port)
                        st.success(f"Ping sent to {target_ip}:{target_port}")
                    else:
                        st.error("IP and Port required.")

        st.subheader(f"Peers ({len(node.peers)})")
        for pid in node.peers:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.code(pid)
            with col2:
                # Add a button for each peer to "Quick Connect"
                if st.button("🔗", key=f"conn_{pid}", help="Fill connection details"):
                    try:
                        # Peer ID is usually "host:port"
                        host, _ = pid.split(":")
                        st.session_state.target_ip = host
                        # Note: We don't know their UDP port from the PID (which is TCP), 
                        # but we can fill the IP to save time.
                        st.rerun()
                    except ValueError:
                        pass

        if st.button("Refresh Network"):
            st.rerun()

    tab1, tab2, tab3 = st.tabs(["💬 Encrypted Chat", "🐝 Artifact Swarm", "🌐 Onion Proxy"])

    with tab1:
        render_chat(node)
    with tab2:
        render_torrent(node)
    with tab3:
        render_proxy(node)

    # Reduce refresh frequency to avoid excessive CPU usage from constant reruns
    time.sleep(10)
    st.rerun()