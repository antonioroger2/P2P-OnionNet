import streamlit as st

def render_chat(node):
    st.subheader("Anonymous Onion Chat")

    # Input
    with st.form("chat_input", clear_on_submit=True):
        msg = st.text_input("Message")
        if st.form_submit_button("Send"):
            node.modules['chat'].send_message(msg)

    # Display
    st.write("---")
    for m in reversed(node.modules['chat'].messages):
        st.text(f"[{m['ts']}] {m['text']}")
