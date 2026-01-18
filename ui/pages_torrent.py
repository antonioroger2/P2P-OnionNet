import streamlit as st

def render_torrent(node):
    st.subheader("Decentralized Swarm")

    # Upload
    uploaded = st.file_uploader("Seed File")
    if uploaded and st.button("Seed"):
        data = uploaded.read()
        f_hash = node.modules['torrent'].add_file(uploaded.name, data)
        st.success(f"Seeding. Magnet Hash: {f_hash}")

    st.divider()

    # List Local Files
    st.write("My Storage:")
    for f_hash, meta in node.modules['torrent'].files.items():
        st.write(f"📄 {meta['name']} (Hash: {f_hash})")
