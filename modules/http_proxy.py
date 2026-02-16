import requests
import json
import uuid

class ProxyModule:
    def __init__(self, node):
        self.node = node
        self.responses = []
        self.pending_sessions = {}  # session_id -> {url, peer}

    def fetch(self, url):
        """
        Client Side: Send a request through the onion network.
        Uses a session ID to reliably route responses back.
        Includes return address as fallback for reply routing.
        """
        my_fp = self.node.pub_key.decode('utf-8')
        session_id = uuid.uuid4().hex[:8]
        
        # Send anonymous request via random peer's circuit
        peers = list(self.node.peers.keys())
        if not peers:
            self.responses.append("[Error] Offline - no peers connected")
            return
        
        random_peer = peers[0] if len(peers) == 1 else __import__('random').choice(peers)
        self.pending_sessions[session_id] = {"url": url, "peer": random_peer}
        
        self.node.send_onion_to_peer(random_peer, "proxy", {
            "type": "request",
            "url": url, 
            "reply_to_fp": my_fp,
            "reply_to_host": self.node.get_local_ip(),
            "reply_to_port": self.node.port,
            "session_id": session_id
        })

    def receive(self, payload):
        """
        Handles both acting as an Exit Node (receiving requests)
        and acting as a Client (receiving website data).
        """
        msg_type = payload.get('type')

        # --- EXIT NODE LOGIC (I am fetching the site for someone else) ---
        if msg_type == "request":
            url = payload.get('url')
            reply_to_fp = payload.get('reply_to_fp')
            reply_to_host = payload.get('reply_to_host')
            reply_to_port = payload.get('reply_to_port')
            session_id = payload.get('session_id', '')
            
            try:
                resp = requests.get(url, timeout=5)
                status_msg = f"Fetched {url} [Status: {resp.status_code}] | Size: {len(resp.content)} bytes"
            except Exception as e:
                status_msg = f"Error fetching {url}: {str(e)}"

            response_payload = {
                "type": "response", 
                "data": status_msg,
                "session_id": session_id
            }

            # Try onion routing first, fallback to direct reply via return address
            target_peer_id = self._find_peer_by_key(reply_to_fp)
            if target_peer_id:
                self.node.send_onion_to_peer(target_peer_id, "proxy", response_payload)
            elif reply_to_host and reply_to_port:
                from core.protocol import MSG_DIRECT
                self.node.send_raw(reply_to_host, int(reply_to_port), MSG_DIRECT, {
                    "module": "proxy", "payload": response_payload
                })

        # --- CLIENT LOGIC (I received the website data I asked for) ---
        elif msg_type == "response":
            session_id = payload.get('session_id', '')
            self.pending_sessions.pop(session_id, None)
            self.responses.append(payload.get('data'))

    def _find_peer_by_key(self, target_pub_key_str):
        """Helper to map a Public Key Fingerprint back to a Peer ID"""
        for pid, meta in self.node.peers.items():
            pub_key = meta.get('pub_key')
            if not pub_key:
                continue
            if isinstance(pub_key, (bytes, bytearray)):
                pub_key_str = pub_key.decode('utf-8')
            else:
                pub_key_str = str(pub_key)
            if pub_key_str == target_pub_key_str:
                return pid
        return None