import streamlit as st

def render_torrent(node):
    st.subheader("Decentralized Swarm")

    # 1. Upload Section
    st.markdown("### 📤 Seed a File")
    uploaded = st.file_uploader("Choose a file to seed", label_visibility="collapsed")
    if uploaded and st.button("Seed File"):
        data = uploaded.read()
        f_hash = node.modules['torrent'].add_file(uploaded.name, data)
        st.success(f"Seeding! Share this Magnet Hash:")
        st.code(f_hash)

    st.divider()

    # 2. Download Section (NEW)
    st.markdown("### 📥 Download from Swarm")
    target_hash = st.text_input("Enter Magnet Hash")
    if st.button("Download File"):
        if target_hash:
            st.info(f"Broadcasting anonymous request for {target_hash}...")
            # This calls our new anonymous request_file method
            node.modules['torrent'].request_file(target_hash)
        else:
            st.warning("Please enter a hash.")

    st.divider()

    # 3. Storage Section
    st.write("### 📂 My Storage")
    if not node.modules['torrent'].files:
        st.caption("No files yet.")
    
    for f_hash, meta in node.modules['torrent'].files.items():
        with st.expander(f"📄 {meta['name']}"):
            st.caption(f"Hash: {f_hash}")
            st.caption(f"Size: {meta['size']} bytes")
            
            # Create a download button for the user to save it to their actual PC
            if f_hash in node.modules['torrent'].chunks:
                st.download_button(
                    label="Save to Disk",
                    data=node.modules['torrent'].chunks[f_hash][0],
                    file_name=meta['name']
                )