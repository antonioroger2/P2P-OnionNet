import socket
import threading
import uuid
import select
from core.protocol import MSG_DIRECT

class ProxyModule:
    def __init__(self, node):
        self.node = node
        self.local_proxy_port = 8080
        self.proxy_running = False
        self.server_sock = None

        # stream_id -> local client socket
        self.client_streams = {}
        # stream_id -> remote target socket (Exit Node side)
        self.exit_streams = {}

    def start_local_proxy(self, port=8080):
        if self.proxy_running: return False
        self.local_proxy_port = port
        self.proxy_running = True

        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(('127.0.0.1', self.local_proxy_port))
        self.server_sock.listen(100)

        threading.Thread(target=self._accept_clients, daemon=True).start()
        return True

    def stop_local_proxy(self):
        self.proxy_running = False
        if self.server_sock:
            self.server_sock.close()

    def _accept_clients(self):
        """Listens for local browser/app connections (HTTP CONNECT Proxy format)."""
        while self.proxy_running:
            try:
                client_sock, addr = self.server_sock.accept()
                threading.Thread(target=self._handle_local_client, args=(client_sock,), daemon=True).start()
            except Exception:
                break

    def _handle_local_client(self, client_sock):
        """Intercepts HTTP CONNECT and sets up the P2P Tunnel."""
        stream_id = None
        try:
            req = client_sock.recv(4096)
            if not req: return

            # Basic HTTP CONNECT parser (Browser HTTPS proxying)
            lines = req.split(b'\r\n')
            first_line = lines[0].decode('utf-8', errors='ignore')

            if first_line.startswith('CONNECT'):
                # Format: CONNECT host:port HTTP/1.1
                target = first_line.split(' ')[1]
                host, port = target.split(':')

                # Tell browser connection is established
                client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

                stream_id = uuid.uuid4().hex
                self.client_streams[stream_id] = client_sock

                # Pick an exit node and initiate stream
                peers = list(self.node.peers.keys())
                if not peers:
                    client_sock.close()
                    return
                import random
                exit_peer = random.choice(peers)

                self.node.send_onion_to_peer(exit_peer, "proxy", {
                    "type": "stream_init",
                    "stream_id": stream_id,
                    "target_host": host,
                    "target_port": int(port),
                    "reply_to_fp": self.node.pub_key.decode('utf-8'),
                    "reply_to_host": self.node.get_local_ip(),
                    "reply_to_port": self.node.port
                })

                # Forward data from Browser -> Onion Network
                while self.proxy_running:
                    data = client_sock.recv(16384)
                    if not data: break
                    self.node.send_onion_to_peer(exit_peer, "proxy", {
                        "type": "stream_data",
                        "stream_id": stream_id,
                        "data": data  # base64 handled by protocol.py
                    })
            else:
                client_sock.close() # Only support CONNECT tunnels for security/simplicity

        except Exception:
            pass
        finally:
            if stream_id:
                self.client_streams.pop(stream_id, None)
            try: client_sock.close()
            except: pass

    def receive(self, payload):
        """Handles Exit Node tunneling and Client Side returning traffic."""
        msg_type = payload.get('type')
        stream_id = payload.get('stream_id')

        # --- EXIT NODE LOGIC ---
        if msg_type == "stream_init":
            target_host = payload.get('target_host')
            target_port = payload.get('target_port')
            reply_fp = payload.get('reply_to_fp')
            reply_host = payload.get('reply_to_host')
            reply_port = payload.get('reply_to_port')

            try:
                # Open socket to actual internet
                remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote_sock.settimeout(5)
                remote_sock.connect((target_host, target_port))
                self.exit_streams[stream_id] = {
                    "sock": remote_sock,
                    "reply_fp": reply_fp,
                    "reply_host": reply_host,
                    "reply_port": reply_port
                }

                # Start thread to push internet data -> Onion Network
                threading.Thread(target=self._exit_node_reader, args=(stream_id,), daemon=True).start()
            except Exception:
                pass # Connection refused by target

        elif msg_type == "stream_data" and stream_id in self.exit_streams:
            # P2P overlay -> Internet Target
            try:
                self.exit_streams[stream_id]["sock"].sendall(payload.get('data'))
            except Exception:
                pass

        # --- CLIENT SIDE LOGIC (Receiving data back from Exit Node) ---
        elif msg_type == "stream_reply" and stream_id in self.client_streams:
            # Exit node -> Local Browser
            try:
                self.client_streams[stream_id].sendall(payload.get('data'))
            except Exception:
                pass

    def _exit_node_reader(self, stream_id):
        """Reads from actual internet and sends back through overlay."""
        meta = self.exit_streams[stream_id]
        sock = meta['sock']

        try:
            while True:
                data = sock.recv(16384)
                if not data: break

                reply_payload = {
                    "type": "stream_reply",
                    "stream_id": stream_id,
                    "data": data
                }

                # Route back to client
                target_peer = self._find_peer_by_key(meta['reply_fp'])
                if target_peer:
                    self.node.send_onion_to_peer(target_peer, "proxy", reply_payload)
                else:
                    self.node.send_raw(meta['reply_host'], int(meta['reply_port']), MSG_DIRECT, {
                        "module": "proxy", "payload": reply_payload
                    })
        except Exception:
            pass
        finally:
            self.exit_streams.pop(stream_id, None)
            try: sock.close()
            except: pass

    def _find_peer_by_key(self, target_pub_key_str):
        for pid, meta in self.node.peers.items():
            p_key = meta.get('pub_key')
            if isinstance(p_key, bytes): p_key = p_key.decode('utf-8')
            if p_key == target_pub_key_str: return pid
        return None