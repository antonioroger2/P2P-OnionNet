import hashlib

class TorrentModule:
    def __init__(self, node):
        self.node = node
        self.chunks = {}  # {file_hash: {index: data}}
        self.files = {}   # {file_hash: metadata}

    def add_file(self, filename, data):
        # Security: Hash the CONTENT, not the filename
        # This prevents "Evil Twin" attacks where bad files have legitimate names.
        f_hash = hashlib.sha256(data).hexdigest()[:16]
        
        self.files[f_hash] = {"name": filename, "size": len(data)}
        self.chunks[f_hash] = {0: data}
        return f_hash

    def request_file(self, f_hash):
        # Step 1: Broadcast a "Request" via Onion Routing to ALL peers.
        # We don't know who has the file, so we ask everyone anonymously.
        # We include our Public Key Fingerprint so the owner can send it back to us.
        # Note: We send our Identity (Key), but NOT our Location (IP).
        my_fp = self.node.pub_key.decode('utf-8')
        
        for peer_id in self.node.peers:
            self.node.send_onion_to_peer(peer_id, "torrent", {
                "action": "request", 
                "hash": f_hash,
                "origin_fp": my_fp
            })

    def receive(self, payload):
        """
        Handles incoming Onion messages.
        Replaces the old insecure 'handle_chunk' method.
        """
        action = payload.get("action")
        
        if action == "request":
            # Someone is asking for a file
            req_hash = payload['hash']
            origin_fp = payload.get('origin_fp')
            
            # Do I have this file?
            if req_hash in self.chunks:
                data = self.chunks[req_hash][0] # Currently handling single-chunk files for MVP
                
                # Find the requester's Peer ID (IP:Port) based on their Fingerprint (origin_fp)
                # We need to know WHICH peer to build an onion circuit to.
                target_peer_id = self._find_peer_by_key(origin_fp)
                
                if target_peer_id:
                    # Send the file back via Onion Circuit (Anonymous Delivery)
                    self.node.send_onion_to_peer(target_peer_id, "torrent", {
                        "action": "response",
                        "hash": req_hash,
                        "data": data
                    })

        elif action == "response":
            # I received a file I asked for!
            f_hash = payload['hash']
            data = payload['data']
            
            # Save the file to memory
            self.chunks[f_hash] = {0: data}
            self.files[f_hash] = {"name": f"Downloaded_{f_hash}", "size": len(data)}

    def _find_peer_by_key(self, target_pub_key_str):
        """Helper to map a Public Key back to an IP:Port string"""
        for pid, meta in self.node.peers.items():
            # In discovery, we store the pem bytes. We compare string representations here.
            if meta.get('pub_key').decode('utf-8') == target_pub_key_str:
                return pid
        return None