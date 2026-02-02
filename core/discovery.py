import socket
import threading
import time
import json
import os
from core.protocol import MSG_HELLO, MSG_PEX, serialize, deserialize

# Security: File to store trusted peer identities
KNOWN_HOSTS_FILE = "known_hosts.json"

# Automated Port Management: 
# If one is blocked by a ghost process, the node automatically tries the other.
PRIMARY_PORT = 49153
FALLBACK_PORT = 49513 

class DiscoveryService(threading.Thread):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.running = True
        self.discovery_port = PRIMARY_PORT
        self.known_hosts = self._load_known_hosts()

    def _load_known_hosts(self):
        """Load trusted peers from disk."""
        if os.path.exists(KNOWN_HOSTS_FILE):
            try:
                with open(KNOWN_HOSTS_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_known_hosts(self):
        """Save trusted peers to disk."""
        try:
            with open(KNOWN_HOSTS_FILE, 'w') as f:
                json.dump(self.known_hosts, f, indent=4)
        except Exception as e:
            print(f"Error saving known_hosts: {e}")

    def run(self):
        """Start the listener and the broadcaster."""
        threading.Thread(target=self.listen_broadcasts, daemon=True).start()
        
        while self.running:
            self.broadcast_presence()
            time.sleep(10) # Rely more on Gossip/PEX than spammy broadcasts

    def broadcast_presence(self):
        """Announce existence to the LAN via UDP."""
        self.send_direct_hello('<broadcast>', is_broadcast=True)

    def manual_connect(self, host, port=None):
        """
        Automated Handshake: Tries both potential discovery ports 
        to ensure the connection works even if a ghost process exists.
        """
        print(f"[PEX] Attempting automated handshake with {host}...")
        for port_to_try in [PRIMARY_PORT, FALLBACK_PORT]:
            self._send_raw_hello(host, port_to_try)

    def _send_raw_hello(self, target_host, target_port):
        """Internal helper to send identity packet."""
        msg = {
            "host": self.node.get_local_ip(),
            "port": self.node.port,
            "pub_key": self.node.pub_key.decode('utf-8')
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(serialize(MSG_HELLO, msg), (target_host, target_port))
            s.close()
        except:
            pass

    def send_direct_hello(self, target_host, is_broadcast=False):
        """Sends identity to the current active discovery port."""
        msg = {
            "host": self.node.get_local_ip(),
            "port": self.node.port,
            "pub_key": self.node.pub_key.decode('utf-8')
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if is_broadcast:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(serialize(MSG_HELLO, msg), (target_host, self.discovery_port))
            s.close()
        except Exception as e:
            print(f"UDP Error: {e}")

    def send_pex(self, target_host):
        """Gossip: Send full known peer list to a target."""
        pex_data = []
        for pid, meta in self.node.peers.items():
            pex_data.append({
                "host": meta['host'],
                "port": meta['port'],
                "pub_key": meta['pub_key'].decode('utf-8') if isinstance(meta['pub_key'], bytes) else meta['pub_key']
            })
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(serialize(MSG_PEX, pex_data), (target_host, self.discovery_port))
            s.close()
        except Exception as e:
            print(f"PEX Send Error: {e}")

    def listen_broadcasts(self):
        """
        Automated Listener with Fallback and Windows Compatibility.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Windows Compatibility: SO_REUSEPORT is only for Unix
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except:
                pass

        # Automatic Resource Recovery: Try primary port, then fallback
        try:
            s.bind(('', self.discovery_port))
        except OSError:
            print(f"[!] Port {self.discovery_port} blocked. Trying fallback...")
            self.discovery_port = FALLBACK_PORT
            try:
                s.bind(('', self.discovery_port))
            except OSError:
                print("[CRITICAL] All discovery ports blocked. Please restart your terminal.")
                return

        print(f"[*] Discovery Service Online: Port {self.discovery_port}")

        while self.running:
            try:
                data, addr = s.recvfrom(65535)
                unpacked = deserialize(data)
                if not unpacked: continue
                
                msg_type, payload = unpacked
                
                if msg_type == MSG_HELLO:
                    if self._validate_and_add_peer(payload):
                        # Introduction handshake: Reply and Gossip
                        self.send_direct_hello(addr[0])
                        self.send_pex(addr[0])
                
                elif msg_type == MSG_PEX:
                    for peer_data in payload:
                        self._validate_and_add_peer(peer_data)

            except Exception as e:
                continue

    def _validate_and_add_peer(self, payload):
        """Identity validation and immediate mesh introduction."""
        peer_host = payload.get('host')
        peer_port = payload.get('port')
        peer_key = payload.get('pub_key')
        peer_id = f"{peer_host}:{peer_port}"

        # 1. Ignore ourselves
        if peer_port == self.node.port and peer_host == self.node.get_local_ip():
            return False

        # 2. TOFU/Identity Check
        if peer_id in self.known_hosts:
            if self.known_hosts[peer_id] != peer_key:
                print(f"[SECURITY] MITM BLOCKED: {peer_id}")
                return False
        else:
            self.known_hosts[peer_id] = peer_key
            self._save_known_hosts()

        # 3. Add to node and signal if it's a new discovery
        if peer_id not in self.node.peers:
            print(f"[PEX] New Peer Discovered: {peer_id}")
            self.node.add_peer(payload)
            return True # Signal for gossip introduction
        
        return False