import socket
from core.relay import RelayService
from core.discovery import DiscoveryService
from core.circuit import CircuitManager
from core.protocol import serialize, MSG_ONION
from core.crypto import generate_rsa_keypair

from modules.chat import ChatModule
from modules.encrypted_torrent import TorrentModule
from modules.http_proxy import ProxyModule

class OnionNode:
    def __init__(self, bind_ip='0.0.0.0'):
        self.bind_ip = bind_ip
        
        self.private_key, self.pub_key = generate_rsa_keypair()
        self.peers = {} 

        self.relay = RelayService(self)
        self.port = self.relay.bind_and_listen(range(6000, 6010), bind_ip=self.bind_ip)
        self.relay.start()

        self.discovery = DiscoveryService(self)
        self.discovery.start()

        self.circuit_mgr = CircuitManager(self)

        self.modules = {
            "chat": ChatModule(self),
            "torrent": TorrentModule(self),
            "proxy": ProxyModule(self)
        }

    def get_local_ip(self):
        if self.bind_ip != '0.0.0.0':
            return self.bind_ip
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return '127.0.0.1'

    def add_peer(self, peer_data):
        pid = f"{peer_data['host']}:{peer_data['port']}"
        self.peers[pid] = peer_data

    def send_raw(self, host, port, msg_type, payload):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((host, port))
            s.send(serialize(msg_type, payload))
            s.close()
        except:
            pass

    def send_onion(self, destination_module, payload):
        circuit = self.circuit_mgr.build_circuit()
        if not circuit: return

        final_payload = {"module": destination_module, "payload": payload}
        onion_packet = self.circuit_mgr.wrap_onion(final_payload, circuit)
        
        entry_node = circuit[0]
        self.send_raw(entry_node['host'], entry_node['port'], MSG_ONION, onion_packet)

    def handle_exit_traffic(self, data):
        module_name = data.get('module')
        content = data.get('payload')

        if module_name in self.modules:
            self.modules[module_name].receive(content)