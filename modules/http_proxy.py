import requests
import json

class ProxyModule:
    def __init__(self, node):
        self.node = node
        self.responses = []

    def fetch(self, url):
        # Send request through onion network
        self.node.send_onion("proxy", {
            "url": url, 
            "origin_host": '127.0.0.1',
            "origin_port": self.node.port,
            "type": "request"
        })

    def receive(self, payload):
        msg_type = payload.get('type')

        if msg_type == "request":
            # --- EXIT NODE LOGIC ---
            url = payload.get('url')
            origin_host = payload.get('origin_host')
            origin_port = payload.get('origin_port')
            
            try:
                # Perform the actual web request
                resp = requests.get(url, timeout=5)
                status_msg = f"Fetched {url} [Status: {resp.status_code}] | Size: {len(resp.content)}b"
            except Exception as e:
                status_msg = f"Error fetching {url}: {str(e)}"

            # Send response DIRECTLY back to the origin (Client)
            # In a full strict onion implementation, this would also be onion-routed back.
            # For this overlay, we use direct TCP callback as per your architectural diag.
            if origin_host and origin_port:
                self.node.send_raw(origin_host, origin_port, "DIRECT", {
                    "module": "proxy",
                    "content": {
                        "type": "response", 
                        "data": status_msg
                    }
                })

        elif msg_type == "response":
            # --- CLIENT LOGIC ---
            self.responses.append(payload.get('data'))