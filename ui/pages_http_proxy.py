import streamlit as st
import streamlit.components.v1 as components

def render_proxy(node):
    st.subheader("Zero-Config In-App Browser")

    st.markdown("""
    **How it works:**
    Enter a URL and click Go. OnionNet sends the request to a random exit peer, fetches HTML remotely,
    and renders the page right here.
    """)

    if "browser_url" not in st.session_state:
        st.session_state.browser_url = "http://example.com"
    if "browser_html" not in st.session_state:
        st.session_state.browser_html = ""
    if "browser_status" not in st.session_state:
        st.session_state.browser_status = None

    with st.form("onion_web_fetch"):
        st.session_state.browser_url = st.text_input("URL", value=st.session_state.browser_url)
        go = st.form_submit_button("Go")

    if go:
        with st.spinner("Fetching through OnionNet exit node..."):
            result = node.modules['proxy'].fetch_url(st.session_state.browser_url)

        if result.get("ok"):
            st.session_state.browser_html = result.get("html", "")
            st.session_state.browser_status = result.get("status_code")
            st.success(f"Loaded via exit node. HTTP status: {st.session_state.browser_status}")
        else:
            st.error(f"Fetch failed: {result.get('error', 'Unknown error')}")

    st.divider()

    if st.session_state.browser_html:
        components.html(st.session_state.browser_html, height=700, scrolling=True)
    else:
        st.info("No page loaded yet. Enter a URL and click Go.")
