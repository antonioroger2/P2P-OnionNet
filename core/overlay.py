import socket
from core.crypto import generate_key
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
    def __init__(self):
        self.pub_key = generate_key()  
        self.private_key, self.pub_key = generate_rsa_keypair()
        self.peers = {}  # { "host:port": {metadata} }

        # Initialize Sub-Systems
        self.relay = RelayService(self)
        self.port = self.relay.bind_and_listen(range(6000, 6010))
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

    def add_peer(self, peer_data):
        pid = f"{peer_data['host']}:{peer_data['port']}"
        self.peers[pid] = peer_data

    def send_raw(self, host, port, msg_type, payload):
        """Low-level TCP send"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.send(serialize(msg_type, payload))
            s.close()
        except:
            pass

    def send_onion(self, destination_module, payload):
        circuit = self.circuit_mgr.build_circuit()
        if not circuit: return

        # 1. Define the final payload (what the Exit node sees)
        final_payload = {"module": destination_module, "payload": payload}
        
        # 2. Wrap it in layers (Exit -> Middle -> Entry)
        onion_packet = self.circuit_mgr.wrap_onion(final_payload, circuit)
        
        # 3. Send to the ENTRY node (First hop)
        entry_node = circuit[0]
        self.send_raw(entry_node['host'], entry_node['port'], MSG_ONION, onion_packet)

    def handle_exit_traffic(self, data):
        """Called when this node is the Exit Node"""
        module_name = data.get('module')
        content = data.get('payload')

        if module_name in self.modules:
            self.modules[module_name].receive(content)