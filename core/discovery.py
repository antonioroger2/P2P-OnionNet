import socket
import threading
import time
import json
import os
from core.protocol import MSG_HELLO, MSG_PEX, serialize, deserialize 

KNOWN_HOSTS_FILE = "known_hosts.json"
DISCOVERY_PORT = 49513 

class DiscoveryService(threading.Thread):
    def __init__(self, node):
        super().__init__()
        # Clean trust on restart for development
        if os.path.exists(KNOWN_HOSTS_FILE):
            try: os.remove(KNOWN_HOSTS_FILE)
            except: pass

        self.node = node
        self.running = True
        self.known_hosts = self._load_known_hosts()

    def _load_known_hosts(self):
        if os.path.exists(KNOWN_HOSTS_FILE):
            try:
                with open(KNOWN_HOSTS_FILE, 'r') as f: return json.load(f)
            except: return {}
        return {}

    def _save_known_hosts(self):
        with open(KNOWN_HOSTS_FILE, 'w') as f:
            json.dump(self.known_hosts, f, indent=4)

    def run(self):
        threading.Thread(target=self.listen_broadcasts, daemon=True).start()
        while self.running:
            self.broadcast_presence()
            time.sleep(10) # Slower broadcast, rely more on Gossip

    def broadcast_presence(self):
        """Standard LAN discovery"""
        self.send_direct_hello('<broadcast>', is_broadcast=True)

    def manual_connect(self, host, port=None):
        """Entry point for manual bootstrap"""
        print(f"[DEBUG] Redirecting manual connect from {host}:{port} to discovery port {DISCOVERY_PORT}")
        self.send_direct_hello(host)

    def send_direct_hello(self, target_host, is_broadcast=False):
        """Sends identity to a specific target"""
        msg = {
            "host": self.node.get_local_ip(),
            "port": self.node.port,
            "pub_key": self.node.pub_key.decode('utf-8')
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if is_broadcast:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(serialize(MSG_HELLO, msg), (target_host, DISCOVERY_PORT))
            s.close()
        except Exception as e:
            print(f"UDP Error: {e}")

    def send_pex(self, target_host):
        """Gossip: Send our known peer list to the target"""
        # Filter peer list to send only necessary metadata
        pex_data = []
        for pid, meta in self.node.peers.items():
            pex_data.append({
                "host": meta['host'],
                "port": meta['port'],
                "pub_key": meta['pub_key'].decode('utf-8')
            })
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(serialize(MSG_PEX, pex_data), (target_host, DISCOVERY_PORT))
            s.close()
        except Exception as e:
            print(f"PEX Send Error: {e}")

    def listen_broadcasts(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            s.bind(('', DISCOVERY_PORT))
        except: return

        while self.running:
            try:
                data, addr = s.recvfrom(65535)
                unpacked = deserialize(data)
                if not unpacked: continue
                
                msg_type, payload = unpacked
                
                if msg_type == MSG_HELLO:
                    # Someone introduced themselves
                    is_new = self._validate_and_add_peer(payload)
                    if is_new:
                        # 1. Reply so they see us
                        self.send_direct_hello(addr[0])
                        # 2. Give them our peer list (Gossip)
                        self.send_pex(addr[0])
                
                elif msg_type == MSG_PEX:
                    # Received a list of peers from a friend
                    for peer_data in payload:
                        self._validate_and_add_peer(peer_data)

            except: continue

    def _validate_and_add_peer(self, payload):
        """TOFU validation and node update"""
        peer_host = payload.get('host')
        peer_port = payload.get('port')
        peer_key = payload.get('pub_key')
        peer_id = f"{peer_host}:{peer_port}"

        if peer_port == self.node.port and peer_host == self.node.get_local_ip():
            return False

        if peer_id in self.known_hosts:
            if self.known_hosts[peer_id] != peer_key:
                print(f"[SECURITY] MITM Blocked: {peer_id}")
                return False
        else:
            self.known_hosts[peer_id] = peer_key
            self._save_known_hosts()
            # If it's a brand new peer, add them and signal for gossip
            self.node.add_peer(payload)
            return True

        self.node.add_peer(payload)
        return False