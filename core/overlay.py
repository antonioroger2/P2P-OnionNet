import socket
import struct
from core.relay import RelayService
from core.discovery import DiscoveryService
from core.circuit import CircuitManager
from core.protocol import serialize, MSG_ONION
from core.crypto import generate_rsa_keypair

# Import Modules
from modules.chat import ChatModule
from modules.encrypted_torrent import TorrentModule
from modules.http_proxy import ProxyModule

class OnionNode:
    def __init__(self, bind_ip='0.0.0.0'):
        self.bind_ip = bind_ip
        
        # Identity
        self.private_key, self.pub_key = generate_rsa_keypair()
        self.peers = {} 

        # Initialize Sub-Systems
        self.relay = RelayService(self)
        # Fix for AttributeError: calling bind_and_listen
        self.port = self.relay.bind_and_listen(range(6000, 6010), bind_ip=self.bind_ip)
        self.relay.start()

        self.discovery = DiscoveryService(self)
        self.discovery.start()
        self.circuit_mgr = CircuitManager(self)

        # Modules
        self.modules = {
            "chat": ChatModule(self),
            "torrent": TorrentModule(self),
            "proxy": ProxyModule(self)
        }

    def send_raw(self, host, port, msg_type, payload):
        """Low-level TCP send with length prefixing to handle large payloads."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((host, port))
            
            data = serialize(msg_type, payload)
            # Prefix with 4-byte network-order length
            packed_data = struct.pack('>I', len(data)) + data
            s.sendall(packed_data)
            s.close()
        except Exception as e:
            print(f"Send failed to {host}:{port} - {e}")

    # ... (Rest of OnionNode methods remain the same as your current overlay.py)
    def add_peer(self, peer_data):
        pid = f"{peer_data['host']}:{peer_data['port']}"
        if isinstance(peer_data['pub_key'], str):
            peer_data['pub_key'] = peer_data['pub_key'].encode('utf-8')
        self.peers[pid] = peer_data

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except:
            return '127.0.0.1'

    def send_onion_to_peer(self, target_peer_id, destination_module, payload):
        if target_peer_id not in self.peers: return
        target = self.peers[target_peer_id]
        circuit = self.circuit_mgr.build_circuit_to_target(target)
        if not circuit: return
        self._dispatch_onion(circuit, destination_module, payload)

    def _dispatch_onion(self, circuit, destination_module, payload):
        final_payload = {"module": destination_module, "payload": payload}
        onion_packet = self.circuit_mgr.wrap_onion(final_payload, circuit)
        entry_node = circuit[0]
        self.send_raw(entry_node['host'], entry_node['port'], MSG_ONION, onion_packet)

    def handle_exit_traffic(self, data):
        module_name = data.get('module')
        content = data.get('payload')
        if module_name in self.modules:
            self.modules[module_name].receive(content)