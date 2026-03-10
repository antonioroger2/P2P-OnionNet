import streamlit as st

def render_torrent(node):
    st.subheader("Decentralized Swarm")

    st.markdown("### 📤 Seed a File")
    uploaded = st.file_uploader("Choose a file to seed", label_visibility="collapsed")
    if uploaded and st.button("Seed File"):
        data = uploaded.read()
        f_hash = node.modules['torrent'].add_file(uploaded.name, data)
        st.success(f"Seeding! Share this Magnet Hash: `{f_hash}`")

    st.divider()

    st.markdown("### 📥 Download from Swarm")
    target_hash = st.text_input("Enter Magnet Hash")
    if st.button("Download File"):
        if target_hash:
            node.modules['torrent'].request_file(target_hash)
            st.info(f"Connecting to peers for {target_hash}...")
        else:
            st.warning("Please enter a hash.")

    st.divider()
    st.write("### 🗃️ Active Transfers & Storage")

    # Combine all known hashes
    all_hashes = set(node.modules['torrent'].files.keys()).union(node.modules['torrent'].pending.keys())
    if not all_hashes:
        st.caption("No files yet.")

    for f_hash in all_hashes:
        status = node.modules['torrent'].file_status.get(f_hash, "unknown")
        meta = node.modules['torrent'].files.get(f_hash) or {}
        is_pending = f_hash in node.modules['torrent'].pending

        # Determine sizes and counts
        total_chunks = meta.get('total') or (node.modules['torrent'].pending[f_hash]['total'] if is_pending else 0)
        have_chunks = len(node.modules['torrent'].chunks.get(f_hash, {}))

        icon = "▶️" if status in ["seeding", "downloading"] else "⏸️" if status == "paused" else "❌" if status == "no_seed" else "⏹️"
        status_color = "green" if status == "seeding" else "blue" if status == "downloading" else "orange" if status == "paused" else "red"

        name_display = meta.get('name', f"Resolving {f_hash[:8]}...")

        with st.expander(f"{icon} {name_display} [:{status_color}[{status.upper()}]]"):
            st.caption(f"Hash: {f_hash}")

            if status == "no_seed":
                st.error("No peers have this file. Check if the hash is correct and peers are connected.")
            elif total_chunks:
                progress = have_chunks / total_chunks
                st.progress(progress)
                st.caption(f"Chunks: {have_chunks}/{total_chunks} ({int(progress*100)}%)")

            col1, col2 = st.columns(2)
            with col1:
                if status == "no_seed":
                    if st.button("Retry Download", key=f"retry_{f_hash}"):
                        node.modules['torrent'].request_file(f_hash)
                        st.rerun()
                else:
                    action_text = "Pause" if status in ["downloading", "seeding"] else "Resume"
                    if st.button(action_text, key=f"btn_{f_hash}"):
                        node.modules['torrent'].toggle_pause(f_hash)
                        st.rerun()

            with col2:
                # Save to disk if complete
                if have_chunks == total_chunks and total_chunks > 0:
                    chunks_dict = node.modules['torrent'].chunks[f_hash]
                    data = b"".join(chunks_dict[i] for i in sorted(chunks_dict.keys()))
                    st.download_button("Save to Disk", data=data, file_name=meta.get('name', f_hash), key=f"dl_{f_hash}")