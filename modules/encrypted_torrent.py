import hashlib
import math
import threading

CHUNK_SIZE = 64 * 1024

class TorrentModule:
    def __init__(self, node):
        self.node = node
        self.chunks = {}  # {file_hash: {index: data}}
        self.files = {}   # {file_hash: metadata}

        # Tracks active downloads: {file_hash: {needed: set(), total: int, peers: {peer_id: [indices]}}}
        self.pending = {}
        self.lock = threading.Lock()

    def add_file(self, filename, data):
        """Split file into chunks and start seeding them."""
        f_hash = hashlib.sha256(data).hexdigest()[:16]

        total = math.ceil(len(data) / CHUNK_SIZE)
        self.files[f_hash] = {"name": filename, "size": len(data), "total": total, "owner_fp": self.node.pub_key.decode('utf-8')}
        self.chunks[f_hash] = {}

        for i in range(total):
            start = i * CHUNK_SIZE
            self.chunks[f_hash][i] = data[start:start + CHUNK_SIZE]

        return f_hash

    def request_file(self, f_hash):
        """Request who has the file and then fetch chunks from peers.

        The protocol:
        - Send `who_has` to all known peers (via onion to each peer).
        - Peers reply with `have` containing their chunk indices and total.
        - On receiving `have`, immediately request chunks from holders (prefer holders
          who report full set of chunks — likely the owner/seeder).
        """
        my_fp = self.node.pub_key.decode('utf-8')

        with self.lock:
            if f_hash in self.pending:
                return
            self.pending[f_hash] = {"needed": set(), "total": None, "peers": {}}

        # Broadcast who_has to all peers
        for peer_id in list(self.node.peers.keys()):
            self.node.send_onion_to_peer(peer_id, "torrent", {
                "action": "who_has",
                "hash": f_hash,
                "origin_fp": my_fp
            })

    def receive(self, payload):
        """Handle incoming torrent-related onion messages."""
        action = payload.get("action")

        if action == "who_has":
            req_hash = payload.get('hash')
            origin_fp = payload.get('origin_fp')

            if req_hash in self.chunks:
                indices = list(self.chunks[req_hash].keys())
                total = self.files.get(req_hash, {}).get('total', len(indices))
                # Reply to the origin (by fingerprint) with what we have
                target_peer_id = self._find_peer_by_key(origin_fp)
                if target_peer_id:
                    self.node.send_onion_to_peer(target_peer_id, "torrent", {
                        "action": "have",
                        "hash": req_hash,
                        "indices": indices,
                        "total": total,
                        "holder_fp": self.node.pub_key.decode('utf-8')
                    })

        elif action == "have":
            f_hash = payload.get('hash')
            indices = payload.get('indices', [])
            total = payload.get('total')
            holder_fp = payload.get('holder_fp')

            with self.lock:
                if f_hash not in self.pending:
                    # Initialize if we didn't explicitly request (late reply)
                    self.pending[f_hash] = {"needed": set(), "total": total, "peers": {}}
                entry = self.pending[f_hash]
                if entry['total'] is None and total is not None:
                    entry['total'] = total
                    entry['needed'] = set(range(total))

            # Map holder_fp to peer_id so we can ask them for chunks
            holder_peer_id = self._find_peer_by_key(holder_fp)
            if not holder_peer_id:
                return

            # Record which indices this peer can provide
            with self.lock:
                entry = self.pending[f_hash]
                entry['peers'][holder_peer_id] = set(indices)

            # Prefer peers who have the full set (seeders / owner)
            if entry.get('total') is not None and len(indices) == entry['total']:
                # Request chunks from this seeder first
                for idx in sorted(list(entry['needed'])):
                    if idx in entry['peers'][holder_peer_id]:
                        self.node.send_onion_to_peer(holder_peer_id, "torrent", {
                            "action": "get_chunk",
                            "hash": f_hash,
                            "index": idx,
                            "origin_fp": self.node.pub_key.decode('utf-8')
                        })
                        break
            else:
                # Request a single chunk we still need from this peer
                with self.lock:
                    needed = entry['needed']
                found = None
                for idx in sorted(list(indices)):
                    if idx in needed:
                        found = idx
                        break
                if found is not None:
                    self.node.send_onion_to_peer(holder_peer_id, "torrent", {
                        "action": "get_chunk",
                        "hash": f_hash,
                        "index": found,
                        "origin_fp": self.node.pub_key.decode('utf-8')
                    })

        elif action == "get_chunk":
            f_hash = payload.get('hash')
            idx = payload.get('index')
            origin_fp = payload.get('origin_fp')

            if f_hash in self.chunks and idx in self.chunks[f_hash]:
                data = self.chunks[f_hash][idx]
                target_peer_id = self._find_peer_by_key(origin_fp)
                if target_peer_id:
                    self.node.send_onion_to_peer(target_peer_id, "torrent", {
                        "action": "chunk",
                        "hash": f_hash,
                        "index": idx,
                        "data": data,
                        "holder_fp": self.node.pub_key.decode('utf-8')
                    })

        elif action == "chunk":
            f_hash = payload.get('hash')
            idx = payload.get('index')
            data = payload.get('data')

            with self.lock:
                entry = self.pending.get(f_hash)
                if not entry:
                    # Unexpected chunk, just store
                    self.chunks.setdefault(f_hash, {})[idx] = data
                    return

                # Save chunk
                self.chunks.setdefault(f_hash, {})[idx] = data
                # Inside the "chunk" action in receive()
                if entry['needed']:
                    # Request the next chunk immediately from known peers
                    next_idx = sorted(list(entry['needed']))[0]
                    # You'll need to track which peer had which chunk in entry['peers']
                    for p_id, p_indices in entry['peers'].items():
                        if next_idx in p_indices:
                            self.node.send_onion_to_peer(p_id, "torrent", {
                                "action": "get_chunk",
                                "hash": f_hash,
                                "index": next_idx,
                                "origin_fp": self.node.pub_key.decode('utf-8')
                            })
                            break
                # If we don't know total yet, try to infer from peers
                if entry['total'] is None:
                    # If any peer previously reported total, use it (already set when we got 'have')
                    pass

                # If download complete, assemble metadata and stop
                if entry['total'] is not None and not entry['needed']:
                    # mark file as downloaded
                    self.files[f_hash] = {"name": f"Downloaded_{f_hash}", "size": sum(len(v) for v in self.chunks[f_hash].values()), "total": entry['total'], "owner_fp": None}
                    # No longer pending
                    del self.pending[f_hash]
    
    def _find_peer_by_key(self, target_pub_key_str):
        for pid, meta in self.node.peers.items():
            current_key = meta.get('pub_key')
            if isinstance(current_key, bytes):
                current_key = current_key.decode('utf-8')
            if current_key == target_pub_key_str:
                return pid
        return None