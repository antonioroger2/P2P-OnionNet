import socket
import threading
import time
import json
import os
from core.protocol import MSG_HELLO, MSG_PEX, serialize, deserialize

# Security: File to store trusted peer identities
KNOWN_HOSTS_FILE = "known_hosts.json"

class DiscoveryService(threading.Thread):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.running = True
        self.discovery_port = 0  # Will be assigned dynamically by OS
        self.known_hosts = self._load_known_hosts()
        
        # DEV MODE: Auto-reset trust
        if os.path.exists(KNOWN_HOSTS_FILE):
            try:
                os.remove(KNOWN_HOSTS_FILE)
            except:
                pass

    def _load_known_hosts(self):
        if os.path.exists(KNOWN_HOSTS_FILE):
            try:
                with open(KNOWN_HOSTS_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_known_hosts(self):
        try:
            with open(KNOWN_HOSTS_FILE, 'w') as f:
                json.dump(self.known_hosts, f, indent=4)
        except:
            pass

    def run(self):
        """Start the listener."""
        threading.Thread(target=self.listen_broadcasts, daemon=True).start()
        
        while self.running:
            # We don't broadcast blindly anymore since ports are random.
            # We rely on Manual Connect + PEX (Gossip).
            time.sleep(5)

    def manual_connect(self, host, target_port):
        """
        Manually connect to a peer's specific UDP Discovery Port.
        """
        if not target_port:
            print("[!] Manual connect failed: No port specified")
            return

        print(f"[MANUAL] Pinging {host}:{target_port}...")
        self._send_raw_hello(host, int(target_port))

    def _send_raw_hello(self, target_host, target_port):
        """Send identity packet to a specific target."""
        msg = {
            "host": self.node.get_local_ip(),
            "port": self.node.port,         # My TCP Data Port
            "pub_key": self.node.pub_key.decode('utf-8')
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(serialize(MSG_HELLO, msg), (target_host, target_port))
            s.close()
        except Exception as e:
            print(f"[!] Send Error: {e}")

    def send_pex(self, target_host, target_port):
        """Gossip: Send peer list to a target."""
        pex_data = []
        for pid, meta in self.node.peers.items():
            pex_data.append({
                "host": meta['host'],
                "port": meta['port'],
                "pub_key": meta['pub_key'].decode('utf-8') if isinstance(meta['pub_key'], bytes) else meta['pub_key']
            })
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(serialize(MSG_PEX, pex_data), (target_host, target_port))
            s.close()
        except:
            pass

    def listen_broadcasts(self):
        """
        Binds to Port 0 (OS Assigned) to avoid blocks.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Windows Compatibility
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except:
                pass

        try:
            # BIND TO PORT 0 -> OS picks a free random port
            s.bind(('', 0))
            self.discovery_port = s.getsockname()[1] # Capture the actual port
            print(f"[*] Discovery Service Listening on UDP Port {self.discovery_port}")
        except Exception as e:
            print(f"[CRITICAL] Bind Failed: {e}")
            return

        while self.running:
            try:
                data, addr = s.recvfrom(65535)
                unpacked = deserialize(data)
                if not unpacked: continue
                
                msg_type, payload = unpacked
                
                if msg_type == MSG_HELLO:
                    if self._validate_and_add_peer(payload):
                        # Reply to the sender so they know us too
                        # Note: We don't know their listening port unless they told us, 
                        # but for UDP hole punching we often reply to addr[1].
                        # For this strict firewall, we assume Manual Connect is 2-way.
                        print(f"[+] Handshake from {addr}")
                
                elif msg_type == MSG_PEX:
                    for peer_data in payload:
                        self._validate_and_add_peer(peer_data)

            except Exception as e:
                continue

    def _validate_and_add_peer(self, payload):
        peer_host = payload.get('host')
        peer_port = payload.get('port')
        peer_key = payload.get('pub_key')
        peer_id = f"{peer_host}:{peer_port}"

        if peer_port == self.node.port and peer_host == self.node.get_local_ip():
            return False

        if peer_id in self.known_hosts:
            if self.known_hosts[peer_id] != peer_key:
                print(f"[SECURITY] BLOCKED MITM: {peer_id}")
                return False
        else:
            self.known_hosts[peer_id] = peer_key
            self._save_known_hosts()

        if peer_id not in self.node.peers:
            print(f"[NEW] Peer Linked: {peer_id}")
            self.node.add_peer(payload)
            return True
        
        return False