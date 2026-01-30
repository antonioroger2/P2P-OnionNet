import requests
import json

class ProxyModule:
    def __init__(self, node):
        self.node = node
        self.responses = []

    def fetch(self, url):
        """
        Client Side: Send a request through the onion network.
        CRITICAL FIX: We do NOT send our IP address. We send a cryptographic fingerprint.
        """
        my_fp = self.node.pub_key.decode('utf-8')
        
        # Send anonymous request via random onion circuit
        self.node.send_onion("proxy", {
            "type": "request",
            "url": url, 
            "reply_to_fp": my_fp  # <--- No IP, just a key identity
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
            
            try:
                # 1. Perform the actual web request (Masking the original user)
                # We use a short timeout to prevent blocking the node
                resp = requests.get(url, timeout=5)
                status_msg = f"Fetched {url} [Status: {resp.status_code}] | Size: {len(resp.content)} bytes"
            except Exception as e:
                status_msg = f"Error fetching {url}: {str(e)}"

            # 2. Send response back ANONYMOUSLY via a new Onion Circuit
            # We look up the peer by their fingerprint, not their IP.
            target_peer_id = self._find_peer_by_key(reply_to_fp)
            
            if target_peer_id:
                self.node.send_onion_to_peer(target_peer_id, "proxy", {
                    "type": "response", 
                    "data": status_msg
                })

        # --- CLIENT LOGIC (I received the website data I asked for) ---
        elif msg_type == "response":
            self.responses.append(payload.get('data'))

    def _find_peer_by_key(self, target_pub_key_str):
        """Helper to map a Public Key Fingerprint back to a Peer ID"""
        for pid, meta in self.node.peers.items():
            if meta.get('pub_key').decode('utf-8') == target_pub_key_str:
                return pid
        return None