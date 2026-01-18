from datetime import datetime

class ChatModule:
    def __init__(self, node):
        self.node = node
        self.messages = []  # List of {timestamp, msg}

    def send_message(self, text):
        # Create Payload
        msg_packet = {
            "text": text, 
            "ts": datetime.now().strftime("%H:%M:%S"),
            "sender_fp": self.node.pub_key.decode('utf-8')[:20] + "..." # Anonymous Fingerprint
        }
        
        # Log locally
        self.messages.append(msg_packet)
        
        # Send via Onion Network
        self.node.send_onion("chat", msg_packet)

    def receive(self, payload):
        # Payload is already a dict thanks to core/protocol.py JSON handling
        self.messages.append(payload)