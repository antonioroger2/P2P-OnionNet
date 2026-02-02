import socket
import threading
import time
import json
import os
from core.protocol import MSG_HELLO, serialize, deserialize

# Security: File to store trusted peer identities (TOFU)
KNOWN_HOSTS_FILE = "known_hosts.json"
DISCOVERY_PORT = 5000  # Standard UDP port for all OnionNet nodes

class DiscoveryService(threading.Thread):
    def __init__(self, node):
        super().__init__()
        
        # --- DEV MODE: AUTO-RESET TRUST ---
        # This prevents "MITM Blocked" errors when restarting nodes during testing.
        # (Since keys regenerate on every restart in this MVP).
        if os.path.exists(KNOWN_HOSTS_FILE):
            try:
                os.remove(KNOWN_HOSTS_FILE)
                print(f"[DEV MODE] Cleared {KNOWN_HOSTS_FILE} for fresh testing.")
            except Exception as e:
                print(f"[DEV MODE] Failed to clear known_hosts: {e}")
        # ----------------------------------

        self.node = node
        self.running = True
        
        # Load known hosts for TOFU validation
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
            time.sleep(5)

    def broadcast_presence(self):
        """Announce our existence to the LAN via UDP."""
        msg = {
            "host": self.node.get_local_ip(),
            "port": self.node.port,
            "pub_key": self.node.pub_key.decode('utf-8')
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(serialize(MSG_HELLO, msg), ('<broadcast>', DISCOVERY_PORT))
            s.close()
        except:
            pass

    def manual_connect(self, host, port):
        """
        Sends a UDP HELLO to the target's Discovery Port (5000).
        """
        msg = {
            "host": self.node.get_local_ip(),
            "port": self.node.port,
            "pub_key": self.node.pub_key.decode('utf-8')
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Ensure the socket can send broadcast if needed, though direct is preferred here
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Send directly to the discovery port of the target host
            s.sendto(serialize(MSG_HELLO, msg), (host, DISCOVERY_PORT))
            s.close()
            print(f"[DEBUG] Manual HELLO sent to {host}:{DISCOVERY_PORT}")
        except Exception as e:
            print(f"Manual connect failed: {e}")
            
    def listen_broadcasts(self):
        """
        Fixed: Properly unpacks the (type, payload) tuple and allows local testing.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            s.bind(('', DISCOVERY_PORT))
        except Exception as e:
            print(f"Discovery port in use: {e}")
            return

        while self.running:
            try:
                data, addr = s.recvfrom(4096)
                unpacked = deserialize(data)
                if unpacked and len(unpacked) == 2:
                    msg_type, payload = unpacked
                    if msg_type == MSG_HELLO:
                        self._validate_and_add_peer(payload)
            except:
                continue

    def _validate_and_add_peer(self, payload):
        """
        Security Logic: Trust-On-First-Use (TOFU)
        """
        peer_host = payload.get('host')
        peer_port = payload.get('port')
        peer_key = payload.get('pub_key')
        
        # Identity is defined by IP:Port
        peer_id = f"{peer_host}:{peer_port}"

        # 1. Ignore ourselves
        if peer_port == self.node.port and peer_host == self.node.get_local_ip():
            return

        # 2. TOFU CHECK
        if peer_id in self.known_hosts:
            stored_key = self.known_hosts[peer_id]
            
            if stored_key != peer_key:
                # MITM DETECTED!
                # The IP is the same, but the Key changed. A hacker is intercepting.
                print(f"\n[SECURITY ALERT] 🚨 MITM BLOCKED! Peer {peer_id} changed keys!")
                return # BLOCK: Do not add to peer list.
        else:
            # First time seeing this peer? Trust them and save.
            print(f"[TOFU] Trusting new peer: {peer_id}")
            self.known_hosts[peer_id] = peer_key
            self._save_known_hosts()

        # 3. If valid, add to node
        self.node.add_peer(payload)