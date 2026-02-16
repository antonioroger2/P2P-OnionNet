import hashlib
import math
import threading

CHUNK_SIZE = 64 * 1024
MAX_RETRIES = 3
RETRY_TIMEOUT = 2.0  # seconds

class TorrentModule:
    def __init__(self, node):
        self.node = node
        self.chunks = {}  
        self.files = {}   
        self.pending = {} 
        self.lock = threading.Lock()
        self._retry_state = {}   # (f_hash, idx) -> retry_count
        self._retry_timers = {}  # (f_hash, idx) -> Timer

    def add_file(self, filename, data):
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
        my_fp = self.node.pub_key.decode('utf-8')
        with self.lock:
            if f_hash not in self.pending:
                self.pending[f_hash] = {"needed": set(), "total": None, "peers": {}}

        for peer_id in list(self.node.peers.keys()):
            self.node.send_onion_to_peer(peer_id, "torrent", {
                "action": "who_has",
                "hash": f_hash,
                "origin_fp": my_fp,
                "origin_host": self.node.get_local_ip(),
                "origin_port": self.node.port
            })

    def receive(self, payload):
        action = payload.get("action")
        my_fp = self.node.pub_key.decode('utf-8')

        if action == "who_has":
            req_hash = payload.get('hash')
            origin_fp = payload.get('origin_fp')
            origin_host = payload.get('origin_host')
            origin_port = payload.get('origin_port')
            if req_hash in self.chunks:
                indices = list(self.chunks[req_hash].keys())
                total = self.files[req_hash]['total']
                response = {
                    "action": "have", "hash": req_hash, 
                    "indices": indices, "total": total, "holder_fp": my_fp
                }
                target_peer_id = self._find_peer_by_key(origin_fp)
                if target_peer_id:
                    self.node.send_onion_to_peer(target_peer_id, "torrent", response)
                elif origin_host and origin_port:
                    # Fallback: direct reply using return address
                    self._send_direct(origin_host, int(origin_port), response)

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
                    # Keep lock held while calling _request_next_chunk to prevent race conditions
                    self._request_next_chunk(f_hash)

        elif action == "get_chunk":
            f_hash = payload.get('hash')
            idx = payload.get('index')
            origin_fp = payload.get('origin_fp')
            origin_host = payload.get('origin_host')
            origin_port = payload.get('origin_port')
            if f_hash in self.chunks and idx in self.chunks[f_hash]:
                response = {
                    "action": "chunk", "hash": f_hash, "index": idx,
                    "data": self.chunks[f_hash][idx], "holder_fp": my_fp
                }
                target_peer_id = self._find_peer_by_key(origin_fp)
                if target_peer_id:
                    self.node.send_onion_to_peer(target_peer_id, "torrent", response)
                elif origin_host and origin_port:
                    # Fallback: direct reply using return address
                    self._send_direct(origin_host, int(origin_port), response)

        elif action == "chunk":
            f_hash = payload.get('hash')
            idx = payload.get('index')
            data = payload.get('data')

            # Cancel any pending retry timer for this chunk
            retry_key = (f_hash, idx)
            timer = self._retry_timers.pop(retry_key, None)
            if timer:
                timer.cancel()
            self._retry_state.pop(retry_key, None)

            with self.lock:
                if f_hash not in self.pending: return
                entry = self.pending[f_hash]

                # Loose verification: accept chunk based on presence, not sender identity
                self.chunks.setdefault(f_hash, {})[idx] = data
                
                # CRITICAL: Mark chunk as received
                entry['needed'].discard(idx)

                if not entry['needed']:
                    self.files[f_hash] = {
                        "name": f"Downloaded_{f_hash}", 
                        "size": sum(len(v) if isinstance(v, (bytes, bytearray)) else len(str(v)) for v in self.chunks[f_hash].values()), 
                        "total": entry['total']
                    }
                    del self.pending[f_hash]
                    self._cleanup_retries(f_hash)
                    print(f"[TORRENT] Download complete: {f_hash}")
                else:
                    self._request_next_chunk(f_hash)

    def _request_next_chunk(self, f_hash):
        """Request the next needed chunk with automatic retry on timeout."""
        # NOTE: Must be called while self.lock is held
        entry = self.pending.get(f_hash)
        if not entry or not entry['needed']: return
        next_idx = sorted(list(entry['needed']))[0]

        retry_key = (f_hash, next_idx)
        if retry_key not in self._retry_state:
            self._retry_state[retry_key] = 0

        for p_id, p_indices in entry['peers'].items():
            if next_idx in p_indices:
                self._send_chunk_request(f_hash, next_idx, p_id)
                # Start a 2-second retry timer
                timer = threading.Timer(RETRY_TIMEOUT, self._retry_chunk, args=(f_hash, next_idx, p_id))
                timer.daemon = True
                timer.start()
                self._retry_timers[retry_key] = timer
                break

    def _send_chunk_request(self, f_hash, idx, p_id):
        """Send a get_chunk request to a specific peer."""
        self.node.send_onion_to_peer(p_id, "torrent", {
            "action": "get_chunk", "hash": f_hash, 
            "index": idx, 
            "origin_fp": self.node.pub_key.decode('utf-8'),
            "origin_host": self.node.get_local_ip(),
            "origin_port": self.node.port
        })

    def _retry_chunk(self, f_hash, idx, p_id):
        """Retry a chunk request if it hasn't arrived within the timeout."""
        with self.lock:
            retry_key = (f_hash, idx)
            if f_hash not in self.pending:
                self._retry_state.pop(retry_key, None)
                return
            entry = self.pending[f_hash]
            if idx not in entry['needed']:
                self._retry_state.pop(retry_key, None)
                return
            
            retries = self._retry_state.get(retry_key, 0)
            if retries >= MAX_RETRIES:
                print(f"[TORRENT] Chunk #{idx} of {f_hash} failed after {MAX_RETRIES} retries")
                self._retry_state.pop(retry_key, None)
                # Try next available chunk instead of blocking
                remaining = entry['needed'] - {idx}
                if remaining:
                    next_idx = sorted(list(remaining))[0]
                    for pid, p_indices in entry['peers'].items():
                        if next_idx in p_indices:
                            self._retry_state[(f_hash, next_idx)] = 0
                            self._send_chunk_request(f_hash, next_idx, pid)
                            t = threading.Timer(RETRY_TIMEOUT, self._retry_chunk, args=(f_hash, next_idx, pid))
                            t.daemon = True
                            t.start()
                            self._retry_timers[(f_hash, next_idx)] = t
                            break
                return
            
            self._retry_state[retry_key] = retries + 1
            print(f"[TORRENT] Retrying chunk #{idx} of {f_hash} (attempt {retries + 1}/{MAX_RETRIES})")
            self._send_chunk_request(f_hash, idx, p_id)
            timer = threading.Timer(RETRY_TIMEOUT, self._retry_chunk, args=(f_hash, idx, p_id))
            timer.daemon = True
            timer.start()
            self._retry_timers[retry_key] = timer

    def _cleanup_retries(self, f_hash):
        """Cancel all pending retry timers for a completed file."""
        keys_to_remove = [k for k in self._retry_timers if k[0] == f_hash]
        for key in keys_to_remove:
            timer = self._retry_timers.pop(key, None)
            if timer:
                timer.cancel()
            self._retry_state.pop(key, None)

    def _send_direct(self, host, port, payload):
        """Send a torrent response directly (non-onion) as a fallback."""
        from core.protocol import MSG_DIRECT
        self.node.send_raw(host, port, MSG_DIRECT, {
            "module": "torrent", "payload": payload
        })

    def _find_peer_by_key(self, target_pub_key_str):
        for pid, meta in self.node.peers.items():
            p_key = meta.get('pub_key')
            if isinstance(p_key, bytes): p_key = p_key.decode('utf-8')
            if p_key == target_pub_key_str: return pid
        return None