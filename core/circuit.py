import random
import json
import base64
from core.crypto import hybrid_encrypt

class CircuitManager:
    def __init__(self, node):
        self.node = node

    def build_circuit(self, hops=3):
        """Dynamic circuit: adapts hop count based on available peers."""
        peers = list(self.node.peers.values())
        if not peers:
            print("[CIRCUIT] No peers available - offline")
            return []
        # Dynamic: degrade gracefully with fewer peers
        effective_hops = min(hops, len(peers))
        if effective_hops < hops:
            print(f"[CIRCUIT] Degraded to {effective_hops}-hop circuit ({len(peers)} peers available)")
        return random.sample(peers, effective_hops)

    def build_circuit_to_target(self, target_peer, hops=3):
        """
        Builds a circuit that ends specifically at 'target_peer'.
        Path: Me -> Random -> Random -> Target
        
        Dynamic hop count: degrades gracefully based on available peers.
        - 0 peers: returns [] (offline)
        - 1-2 peers: 1-hop direct circuit to target
        - 3+ peers: full multi-hop onion circuit
        """
        peers = list(self.node.peers.values())
        if not peers:
            print("[CIRCUIT] No peers available - offline")
            return []

        # Dynamic hop count based on peer availability
        effective_hops = min(hops, len(peers))
        if effective_hops < hops:
            print(f"[CIRCUIT] Degraded to {effective_hops}-hop circuit ({len(peers)} peers available)")

        # 1. Start with the target as the Exit Node
        circuit = [target_peer]
        
        # 2. Fill the rest with random middle nodes
        available_middle = [p for p in peers if p != target_peer]
        needed = effective_hops - 1
        if needed > 0:
            if len(available_middle) >= needed:
                circuit = random.sample(available_middle, needed) + circuit
            else:
                circuit = available_middle + circuit

        return circuit

    def wrap_onion(self, final_payload, circuit):
        """
        Wraps message in layers: Enc_A( IP_B, Enc_B( IP_C, Enc_C( Payload ) ) )
        """
        # Serialize the initial payload to bytes (JSON)
        message_bytes = json.dumps(final_payload).encode('utf-8')

        # Logic: We start from the Exit node and wrap backwards to the Entry node.
        next_hop_addr = None  

        for peer in reversed(circuit):
            # 1. Construct the layer content
            layer_content = {
                "next_hop": next_hop_addr, 
                "data_b64": base64.b64encode(message_bytes).decode('utf-8')
            }
            
            # 2. Serialize and Encrypt
            serialized_layer = json.dumps(layer_content).encode('utf-8')
            message_bytes = hybrid_encrypt(serialized_layer, peer['pub_key'])
            
            # 3. Set next_hop for the *next* iteration
            next_hop_addr = (peer['host'], peer['port'])

        return message_bytes