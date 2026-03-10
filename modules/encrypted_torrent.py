import hashlib
import math
import threading

CHUNK_SIZE = 64 * 1024
MAX_RETRIES = 3
RETRY_TIMEOUT = 2.0

class TorrentModule:
    def __init__(self, node):
        self.node = node
        self.chunks = {}  
        self.files = {}   
        self.pending = {} 
        self.file_status = {} # NEW: Tracks 'downloading', 'paused', 'seeding', 'stopped'
        self.lock = threading.Lock()
        self._retry_state = {}   
        self._retry_timers = {}  

    def add_file(self, filename, data):
        f_hash = hashlib.sha256(data).hexdigest()[:16]
        total = math.ceil(len(data) / CHUNK_SIZE)
        
        self.files[f_hash] = {
            "name": filename, 
            "size": len(data), 
            "total": total, 
            "owner_fp": self.node.pub_key.decode('utf-8')
        }
        self.file_status[f_hash] = "seeding" # Auto-seed on creation
        
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
            self.file_status[f_hash] = "downloading"

        self._broadcast_who_has(f_hash)
        # Start timeout for seed discovery
        timer = threading.Timer(10.0, self._check_seed_timeout, args=(f_hash,))
        timer.daemon = True
        timer.start()

    def _broadcast_who_has(self, f_hash):
        my_fp = self.node.pub_key.decode('utf-8')
        for peer_id in list(self.node.peers.keys()):
            self.node.send_onion_to_peer(peer_id, "torrent", {
                "action": "who_has", "hash": f_hash,
                "origin_fp": my_fp,
                "origin_host": self.node.get_local_ip(),
                "origin_port": self.node.port
            })

    def toggle_pause(self, f_hash):
        """Toggles between paused and downloading/seeding state."""
        with self.lock:
            current = self.file_status.get(f_hash)
            if current == "downloading":
                self.file_status[f_hash] = "paused"
                self._cleanup_retries(f_hash) # Stop active requests
            elif current == "paused":
                if f_hash in self.pending and self.pending[f_hash]['needed']:
                    self.file_status[f_hash] = "downloading"
                    self._broadcast_who_has(f_hash) # Resume finding peers
                else:
                    self.file_status[f_hash] = "seeding"
            elif current == "seeding":
                self.file_status[f_hash] = "stopped"
            elif current == "stopped":
                self.file_status[f_hash] = "seeding"
            elif current == "no_seed":
                # Retry download
                self.file_status[f_hash] = "downloading"
                self._broadcast_who_has(f_hash)
                timer = threading.Timer(10.0, self._check_seed_timeout, args=(f_hash,))
                timer.daemon = True
                timer.start()

    def receive(self, payload):
        action = payload.get("action")
        my_fp = self.node.pub_key.decode('utf-8')

        if action == "who_has":
            req_hash = payload.get('hash')
            # Only respond if we have chunks AND we are actively seeding/downloading (partial seeding enabled)
            if req_hash in self.chunks and self.file_status.get(req_hash) in ["seeding", "downloading"]:
                indices = list(self.chunks[req_hash].keys())
                total = self.files.get(req_hash, {}).get('total') or self.pending.get(req_hash, {}).get('total')
                if not total: return

                response = {
                    "action": "have", "hash": req_hash, 
                    "indices": indices, "total": total, "holder_fp": my_fp
                }
                self._reply_to_origin(payload, response)

        elif action == "have":
            f_hash = payload.get('hash')
            # If was no_seed, now we found peers
            if self.file_status.get(f_hash) == "no_seed":
                self.file_status[f_hash] = "downloading"
            # Ignore if paused
            if self.file_status.get(f_hash) != "downloading": return

            with self.lock:
                if f_hash not in self.pending: return
                entry = self.pending[f_hash]
                if entry['total'] is None:
                    entry['total'] = payload.get('total')
                    # Populate needed with everything we DON'T currently have
                    existing_chunks = set(self.chunks.get(f_hash, {}).keys())
                    entry['needed'] = set(range(payload.get('total'))) - existing_chunks
                
                holder_peer_id = self._find_peer_by_key(payload.get('holder_fp'))
                if holder_peer_id:
                    entry['peers'][holder_peer_id] = set(payload.get('indices', []))
                    self._request_next_chunk(f_hash)

        elif action == "get_chunk":
            f_hash = payload.get('hash')
            idx = payload.get('index')
            # Only serve chunks if we aren't paused/stopped
            if self.file_status.get(f_hash) not in ["seeding", "downloading"]: return

            if f_hash in self.chunks and idx in self.chunks[f_hash]:
                response = {
                    "action": "chunk", "hash": f_hash, "index": idx,
                    "data": self.chunks[f_hash][idx], "holder_fp": my_fp
                }
                self._reply_to_origin(payload, response)

        elif action == "chunk":
            f_hash = payload.get('hash')
            if self.file_status.get(f_hash) != "downloading": return

            idx = payload.get('index')
            data = payload.get('data')

            self._cancel_timer(f_hash, idx)

            with self.lock:
                if f_hash not in self.pending: return
                entry = self.pending[f_hash]

                self.chunks.setdefault(f_hash, {})[idx] = data
                entry['needed'].discard(idx)

                if not entry['needed']:
                    self.files[f_hash] = {
                        "name": f"Downloaded_{f_hash}", 
                        "size": sum(len(v) if isinstance(v, (bytes, bytearray)) else len(str(v)) for v in self.chunks[f_hash].values()), 
                        "total": entry['total']
                    }
                    self.file_status[f_hash] = "seeding" # Auto-transition to seeding
                    del self.pending[f_hash]
                    self._cleanup_retries(f_hash)
                    print(f"[TORRENT] Download complete: {f_hash}")
                else:
                    self._request_next_chunk(f_hash)

    def _reply_to_origin(self, original_payload, response_payload):
        target_peer_id = self._find_peer_by_key(original_payload.get('origin_fp'))
        if target_peer_id:
            self.node.send_onion_to_peer(target_peer_id, "torrent", response_payload)
        elif original_payload.get('origin_host'):
            from core.protocol import MSG_DIRECT
            self.node.send_raw(original_payload['origin_host'], int(original_payload['origin_port']), MSG_DIRECT, {
                "module": "torrent", "payload": response_payload
            })

    def _request_next_chunk(self, f_hash):
        entry = self.pending.get(f_hash)
        if not entry or not entry['needed'] or self.file_status.get(f_hash) != "downloading": return
        next_idx = sorted(list(entry['needed']))[0]

        retry_key = (f_hash, next_idx)
        if retry_key not in self._retry_state: self._retry_state[retry_key] = 0

        for p_id, p_indices in entry['peers'].items():
            if next_idx in p_indices:
                self._send_chunk_request(f_hash, next_idx, p_id)
                timer = threading.Timer(RETRY_TIMEOUT, self._retry_chunk, args=(f_hash, next_idx, p_id))
                timer.daemon = True; timer.start()
                self._retry_timers[retry_key] = timer
                break

    def _send_chunk_request(self, f_hash, idx, p_id):
        self.node.send_onion_to_peer(p_id, "torrent", {
            "action": "get_chunk", "hash": f_hash, "index": idx, 
            "origin_fp": self.node.pub_key.decode('utf-8'),
            "origin_host": self.node.get_local_ip(), "origin_port": self.node.port
        })

    def _retry_chunk(self, f_hash, idx, p_id):
        with self.lock:
            if self.file_status.get(f_hash) != "downloading": return
            retry_key = (f_hash, idx)
            entry = self.pending.get(f_hash)
            if not entry or idx not in entry['needed']: return
            
            retries = self._retry_state.get(retry_key, 0)
            if retries >= MAX_RETRIES:
                self._retry_state.pop(retry_key, None)
                remaining = entry['needed'] - {idx}
                if remaining:
                    next_idx = sorted(list(remaining))[0]
                    self._request_next_chunk(f_hash) # Move to next chunk
                return
            
            self._retry_state[retry_key] = retries + 1
            self._send_chunk_request(f_hash, idx, p_id)
            timer = threading.Timer(RETRY_TIMEOUT, self._retry_chunk, args=(f_hash, idx, p_id))
            timer.daemon = True; timer.start()
            self._retry_timers[retry_key] = timer

    def _cancel_timer(self, f_hash, idx):
        timer = self._retry_timers.pop((f_hash, idx), None)
        if timer: timer.cancel()
        self._retry_state.pop((f_hash, idx), None)

    def _cleanup_retries(self, f_hash):
        keys = [k for k in self._retry_timers if k[0] == f_hash]
        for k in keys: self._cancel_timer(*k)

    def _check_seed_timeout(self, f_hash):
        with self.lock:
            if f_hash not in self.pending:
                return
            entry = self.pending[f_hash]
            if entry['peers']:
                return  # Peers found, continue
            # No peers responded, mark as no seed
            self.file_status[f_hash] = "no_seed"
            print(f"[TORRENT] No seed found for {f_hash}, stopping download.")