import streamlit as st

def render_proxy(node):
    st.subheader("Exit Node Fetcher")

    url = st.text_input("Target URL")
    if st.button("Fetch via Onion Circuit"):
        node.modules['proxy'].fetch(url)
        st.info("Request sent through circuit.")

    st.write("---")
    st.write("Exit Node Logs:")
    for resp in node.modules['proxy'].responses:
        st.code(resp)
