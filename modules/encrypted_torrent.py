import hashlib

class TorrentModule:
    def __init__(self, node):
        self.node = node
        self.chunks = {}  # {file_hash: {index: data}}
        self.files = {}   # {file_hash: metadata}

    def add_file(self, filename, data):
        # Security Fix: Hash the CONTENT, not the filename
        # This prevents "Evil Twin" attacks where bad files have legitimate names.
        f_hash = hashlib.sha256(data).hexdigest()[:16]
        
        self.files[f_hash] = {"name": filename, "size": len(data)}
        self.chunks[f_hash] = {0: data}
        return f_hash

    def request_file(self, f_hash):
        # Ask peers for this file, including my port for the reply
        for peer in self.node.peers.values():
            self.node.send_raw(peer['host'], peer['port'], "FILE_CHUNK", {
                "action": "request", 
                "hash": f_hash,
                "origin_port": self.node.port
            })

    def handle_chunk(self, payload):
        action = payload.get("action")
        
        if action == "request":
            req_hash = payload['hash']
            origin_port = payload.get('origin_port')
            
            # If I have the file, send it back
            if req_hash in self.chunks and origin_port:
                data = self.chunks[req_hash][0] # Sending chunk 0
                self.node.send_raw('127.0.0.1', origin_port, "FILE_CHUNK", {
                    "action": "response",
                    "hash": req_hash,
                    "data": data
                })
        
        elif action == "response":
            # I received a file chunk
            f_hash = payload['hash']
            data = payload['data']
            # Store it (simplified)
            self.chunks[f_hash] = {0: data}
            self.files[f_hash] = {"name": f"Downloaded_{f_hash}", "size": len(data)}