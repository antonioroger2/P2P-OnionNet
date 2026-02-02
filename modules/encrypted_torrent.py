import hashlib
import math
import threading
import base64

CHUNK_SIZE = 64 * 1024

class TorrentModule:
    def __init__(self, node):
        self.node = node
        self.chunks = {}  # {file_hash: {index: data}}
        self.files = {}   # {file_hash: metadata}
        self.pending = {} # {file_hash: {needed: set, total: int, peers: {}}}
        self.lock = threading.Lock()

    def add_file(self, filename, data):
        """Owner Action: Splits file into chunks and makes them available for others."""
        f_hash = hashlib.sha256(data).hexdigest()[:16]
        total = math.ceil(len(data) / CHUNK_SIZE)
        
        self.files[f_hash] = {
            "name": filename, 
            "size": len(data), 
            "total": total, 
            "owner_fp": self.node.pub_key.decode('utf-8')
        }
        
        self.chunks[f_hash] = {}
        for i in range(total):
            start = i * CHUNK_SIZE
            self.chunks[f_hash][i] = data[start:start + CHUNK_SIZE]
        
        return f_hash

    def request_file(self, f_hash):
        """Downloader Action: Broadcasts a request to find who has the file."""
        my_fp = self.node.pub_key.decode('utf-8')
        with self.lock:
            # Initialize download state for this hash
            if f_hash not in self.pending:
                self.pending[f_hash] = {"needed": set(), "total": None, "peers": {}}

        # Ask all known peers if they are seeding this hash
        for peer_id in list(self.node.peers.keys()):
            self.node.send_onion_to_peer(peer_id, "torrent", {
                "action": "who_has",
                "hash": f_hash,
                "origin_fp": my_fp
            })

    def receive(self, payload):
        """Unified Handler for all P2P Torrenting traffic."""
        action = payload.get("action")
        my_fp = self.node.pub_key.decode('utf-8')

        # 1. OWNER SIDE: Someone is asking if I have a file
        if action == "who_has":
            req_hash = payload.get('hash')
            origin_fp = payload.get('origin_fp')
            if req_hash in self.chunks:
                indices = list(self.chunks[req_hash].keys())
                total = self.files[req_hash]['total']
                target_peer_id = self._find_peer_by_key(origin_fp)
                if target_peer_id:
                    # Tell the requester I have the file
                    self.node.send_onion_to_peer(target_peer_id, "torrent", {
                        "action": "have",
                        "hash": req_hash,
                        "indices": indices,
                        "total": total,
                        "holder_fp": my_fp
                    })

        # 2. DOWNLOADER SIDE: A peer told me they have chunks
        elif action == "have":
            f_hash = payload.get('hash')
            indices = payload.get('indices', [])
            total = payload.get('total')
            holder_fp = payload.get('holder_fp')

            with self.lock:
                if f_hash not in self.pending: return
                entry = self.pending[f_hash]
                if entry['total'] is None:
                    entry['total'] = total
                    entry['needed'] = set(range(total))
                
                holder_peer_id = self._find_peer_by_key(holder_fp)
                if holder_peer_id:
                    entry['peers'][holder_peer_id] = set(indices)
                    self._request_next_chunk(f_hash)

        # 3. OWNER SIDE: Someone is requesting a specific chunk from me
        elif action == "get_chunk":
            f_hash = payload.get('hash')
            idx = payload.get('index')
            origin_fp = payload.get('origin_fp')
            if f_hash in self.chunks and idx in self.chunks[f_hash]:
                target_peer_id = self._find_peer_by_key(origin_fp)
                if target_peer_id:
                    # Serve the data chunk anonymously through an onion circuit
                    self.node.send_onion_to_peer(target_peer_id, "torrent", {
                        "action": "chunk",
                        "hash": f_hash,
                        "index": idx,
                        "data": self.chunks[f_hash][idx],
                        "holder_fp": my_fp
                    })

        # 4. DOWNLOADER SIDE: I received a chunk of data
        elif action == "chunk":
            f_hash = payload.get('hash')
            idx = payload.get('index')
            data = payload.get('data')

            with self.lock:
                if f_hash not in self.pending: return
                entry = self.pending[f_hash]
                
                self.chunks.setdefault(f_hash, {})[idx] = data
                entry['needed'].discard(idx) # Mark this chunk as completed

                if not entry['needed']:
                    # Reassemble metadata once download is 100%
                    self.files[f_hash] = {
                        "name": f"Downloaded_{f_hash}", 
                        "size": sum(len(v) for v in self.chunks[f_hash].values()), 
                        "total": entry['total'], 
                        "owner_fp": None
                    }
                    del self.pending[f_hash]
                else:
                    self._request_next_chunk(f_hash)

    def _request_next_chunk(self, f_hash):
        """Internal logic to fetch chunks sequentially from available peers."""
        entry = self.pending[f_hash]
        if not entry['needed']: return

        next_idx = sorted(list(entry['needed']))[0]
        for p_id, p_indices in entry['peers'].items():
            if next_idx in p_indices:
                self.node.send_onion_to_peer(p_id, "torrent", {
                    "action": "get_chunk",
                    "hash": f_hash,
                    "index": next_idx,
                    "origin_fp": self.node.pub_key.decode('utf-8')
                })
                break

    def _find_peer_by_key(self, target_pub_key_str):
        """Maps a Public Key Fingerprint to an active Peer ID."""
        for pid, meta in self.node.peers.items():
            p_key = meta.get('pub_key')
            if isinstance(p_key, bytes):
                p_key = p_key.decode('utf-8')
            if p_key == target_pub_key_str:
                return pid
        return None