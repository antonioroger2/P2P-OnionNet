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
        
        # Broadcast via Onion Network to ALL peers
        # We iterate through the peer list and send a targeted onion to each.
        # This ensures everyone receives the message anonymously.
        for peer_id in self.node.peers:
            self.node.send_onion_to_peer(peer_id, "chat", msg_packet)

    def receive(self, payload):
        # Deduplication could go here, but for MVP we just append
        self.messages.append(payload)