import socket
import threading
import time
import json
import os
import random
import errno
from core.protocol import MSG_HELLO, MSG_PEX, serialize, deserialize

KNOWN_HOSTS_FILE = "known_hosts.json"


BOOTSTRAP_NODES = [
    # ("1.2.3.4", 5000),  # Example: uncomment and set to a real bootstrap node
]

class DiscoveryService(threading.Thread):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.running = True
        self.discovery_port = 0  # Will be assigned dynamically by OS
        self.known_hosts = self._load_known_hosts()
        
        # DEV MODE: Auto-reset trust (only when explicitly enabled)
        if os.getenv("DISCOVERY_DEV_MODE") == "1":
            if os.path.exists(KNOWN_HOSTS_FILE):
                try:
                    os.remove(KNOWN_HOSTS_FILE)
                    print("[DEV MODE] Cleared known_hosts.json for testing")
                except OSError as e:
                    print(f"[DiscoveryService] Failed to remove {KNOWN_HOSTS_FILE}: {e}")

    def _load_known_hosts(self):
        if os.path.exists(KNOWN_HOSTS_FILE):
            try:
                with open(KNOWN_HOSTS_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, OSError) as e:
                print(f"[ERROR] Failed to load known_hosts.json: {e}")
                return {}
        return {}

    def _save_known_hosts(self):
        try:
            with open(KNOWN_HOSTS_FILE, 'w') as f:
                json.dump(self.known_hosts, f, indent=4)
        except (IOError, OSError) as e:
            print(f"[ERROR] Failed to save known_hosts.json: {e}")

    def run(self):
        """Start the listener."""
        threading.Thread(target=self.listen_broadcasts, daemon=True).start()
        
        # Auto-connect to bootstrap nodes on startup
        time.sleep(1)  # Wait briefly for listener to bind
        for host, port in BOOTSTRAP_NODES:
            print(f"[BOOTSTRAP] Connecting to {host}:{port}...")
            self._send_raw_hello(host, port)
        
        while self.running:
            # Periodically gossip peer lists to all known peers
            self._gossip_round()
            time.sleep(30)

    def _gossip_round(self):
        """Periodically share our peer list with all known peers."""
        if not self.node.peers:
            return
        for pid, meta in list(self.node.peers.items()):
            disc_port = meta.get('discovery_port')
            if disc_port:
                self.send_pex(meta['host'], disc_port)

    def manual_connect(self, host, target_port):
        """
        Manually connect to a peer's specific UDP Discovery Port.
        """
        if not target_port:
            print("[!] Manual connect failed: No port specified")
            return

        try:
            port = int(target_port)
        except ValueError:
            print(f"[!] Manual connect failed: Invalid port '{target_port}'. Port must be a number.")
            return

        print(f"[MANUAL] Pinging {host}:{port}...")
        self._send_raw_hello(host, port)

    def _send_raw_hello(self, target_host, target_port):
        """Send identity packet to a specific target, including gossip peers."""
        # Attach up to 5 random peers for gossip
        gossip_peers = []
        peer_list = list(self.node.peers.values())
        sample_size = min(5, len(peer_list))
        if sample_size > 0:
            for p in random.sample(peer_list, sample_size):
                gossip_peers.append({
                    "host": p['host'],
                    "port": p['port'],
                    "discovery_port": p.get('discovery_port'),
                    "pub_key": p['pub_key'].decode('utf-8') if isinstance(p['pub_key'], bytes) else p['pub_key']
                })

        msg = {
            "host": self.node.get_local_ip(),
            "port": self.node.port,             # My TCP Data Port
            "discovery_port": self.discovery_port,  # My UDP Discovery Port
            "pub_key": self.node.pub_key.decode('utf-8'),
            "gossip_peers": gossip_peers
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(serialize(MSG_HELLO, msg), (target_host, target_port))
            s.close()
        except OSError as e:
            # FIX: Suppress "Network is unreachable" which is common in some setups
            if e.errno == errno.ENETUNREACH:
                print(f"[WARN] Network unreachable when sending Hello to {target_host}")
            else:
                print(f"[!] Send Error: {e}")
        except Exception as e:
            print(f"[!] Send Error: {e}")

    def send_pex(self, target_host, target_port):
        """Gossip: Send peer list to a target."""
        pex_data = []
        for pid, meta in self.node.peers.items():
            pex_data.append({
                "host": meta['host'],
                "port": meta['port'],
                "discovery_port": meta.get('discovery_port'),
                "pub_key": meta['pub_key'].decode('utf-8') if isinstance(meta['pub_key'], bytes) else meta['pub_key']
            })
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(serialize(MSG_PEX, pex_data), (target_host, target_port))
            s.close()
        except OSError as e:
            # FIX: Suppress network unreachable errors
            if e.errno == errno.ENETUNREACH:
                pass 
            else:
                print(f"[ERROR] Failed to send PEX: {e}")

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
            except OSError:
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

                msg_type = unpacked.get('type')
                payload = unpacked.get('payload')
                
                if msg_type == MSG_HELLO:
                    # Extract gossip peers before adding the sender
                    gossip_peers = payload.pop('gossip_peers', [])
                    sender_disc_port = payload.get('discovery_port')

                    if self._validate_and_add_peer(payload):
                        print(f"[+] Handshake from {addr}")
                        # Reply so the sender knows us too
                        if sender_disc_port:
                            self._send_raw_hello(addr[0], sender_disc_port)
                    
                    # Auto-discover gossip peers we don't know yet
                    for gp in gossip_peers:
                        gp_id = f"{gp['host']}:{gp['port']}"
                        if gp_id not in self.node.peers:
                            gp_copy = {k: v for k, v in gp.items() if k != 'discovery_port'}
                            gp_copy['discovery_port'] = gp.get('discovery_port')
                            self._validate_and_add_peer(gp_copy)
                            gp_disc = gp.get('discovery_port')
                            if gp_disc:
                                self._send_raw_hello(gp['host'], gp_disc)

                elif msg_type == MSG_PEX:
                    for peer_data in payload:
                        if self._validate_and_add_peer(peer_data):
                            disc_port = peer_data.get('discovery_port')
                            if disc_port:
                                self._send_raw_hello(peer_data['host'], disc_port)

            except Exception as e:
                print(f"[ERROR] DiscoveryService listen_broadcasts exception: {e}")
                continue

    def _validate_and_add_peer(self, payload):
        peer_host = payload.get('host')
        peer_port = payload.get('port')
        peer_key = payload.get('pub_key')
        peer_id = f"{peer_host}:{peer_port}"

        if peer_port == self.node.port and peer_host == self.node.get_local_ip():
            return False

        # TOFU: Use host (without port) as the stable identifier
        trusted_id = peer_host
        
        if trusted_id in self.known_hosts:
            if self.known_hosts[trusted_id] != peer_key:
                print(f"[SECURITY] BLOCKED MITM: {peer_id} (key mismatch for {trusted_id})")
                return False
        else:
            self.known_hosts[trusted_id] = peer_key
            self._save_known_hosts()

        if peer_id not in self.node.peers:
            print(f"[NEW] Peer Linked: {peer_id}")
            self.node.add_peer(payload)
            return True
        
        return False