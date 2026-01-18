import random
import json
import base64
from core.crypto import hybrid_encrypt

class CircuitManager:
    def __init__(self, node):
        self.node = node

    def build_circuit(self, hops=3):
        """Selects random peers to form a path."""
        peers = list(self.node.peers.values())
        if len(peers) < hops:
            return peers  # Short circuit if not enough peers
        return random.sample(peers, hops)

    def wrap_onion(self, final_payload, circuit):
        """
        Wraps message in layers: Enc_A( IP_B, Enc_B( IP_C, Enc_C( Payload ) ) )
        """
        # Serialize the initial payload to bytes (JSON)
        # This payload is what the Exit Node will see.
        message_bytes = json.dumps(final_payload).encode('utf-8')

        # Logic: We start from the Exit node and wrap backwards to the Entry node.
        # This ensures that when the Entry node peels its layer, it sees the Middle node's address.
        
        next_hop_addr = None  # The Exit node has no next hop (it processes the data)

        for peer in reversed(circuit):
            # 1. Construct the layer content
            layer_content = {
                "next_hop": next_hop_addr, 
                "data_b64": base64.b64encode(message_bytes).decode('utf-8')
            }
            
            # 2. Serialize this layer to bytes so it can be encrypted
            serialized_layer = json.dumps(layer_content).encode('utf-8')
            
            # 3. Encrypt for the current node using their Public Key
            message_bytes = hybrid_encrypt(serialized_layer, peer['pub_key'])
            
            # 4. Set next_hop for the *next* iteration (previous node in the path)
            # This node (peer) will be the 'next_hop' for the node before it.
            next_hop_addr = (peer['host'], peer['port'])

        return message_bytes