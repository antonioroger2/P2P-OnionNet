import streamlit as st

def render_proxy(node):
    st.subheader("P2P Proxy Tunnel (Exit Node Routing)")

    st.markdown("""
    **How it works:**
    Turn on the Local Proxy below. Then, configure your OS or Browser (e.g., Firefox Proxy Settings) 
    to use **HTTP Proxy: `127.0.0.1`** with the port below. All your HTTPS traffic will be multiplexed 
    and routed through random peers on OnionNet.
    """)

    col1, col2 = st.columns(2)
    with col1:
        port = st.number_input("Local Port", value=8080, min_value=1024, max_value=65535)

    with col2:
        st.write("") # spacing
        st.write("")
        if node.modules['proxy'].proxy_running:
            if st.button("🛑 Stop Proxy Server"):
                node.modules['proxy'].stop_local_proxy()
                st.rerun()
        else:
            if st.button("🚀 Start Proxy Server"):
                success = node.modules['proxy'].start_local_proxy(int(port))
                if success:
                    st.rerun()
                else:
                    st.error("Failed to bind port. Try another.")

    st.divider()

    if node.modules['proxy'].proxy_running:
        st.success(f"🟢 Proxy listening on **127.0.0.1:{node.modules['proxy'].local_proxy_port}**")

        st.write("### Active Multiplexed Streams")
        client_streams = len(node.modules['proxy'].client_streams)
        exit_streams = len(node.modules['proxy'].exit_streams)

        st.metric("My Browsing Streams (Client)", client_streams)
        st.metric("Relaying for Others (Exit Node)", exit_streams)
    else:
        st.warning("🔴 Proxy is currently Offline")
