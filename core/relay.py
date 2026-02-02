import socket
import threading
import json
import base64
import struct
from core.protocol import deserialize, MSG_HELLO, MSG_ONION, MSG_CHUNK, MSG_DIRECT
from core.crypto import hybrid_decrypt

class RelayService:
    def __init__(self, node):
        self.node = node
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = True

    def bind_and_listen(self, port_range, bind_ip='0.0.0.0'):
        """Attempts to bind the node to an available port in the range."""
        for port in port_range:
            try:
                self.sock.bind((bind_ip, port))
                self.sock.listen(5)
                return port
            except OSError:
                continue
        raise RuntimeError("No free ports available.")

    def start(self):
        threading.Thread(target=self._listener, daemon=True).start()

    def _listener(self):
        while self.running:
            try:
                conn, addr = self.sock.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except:
                break

    def _handle(self, conn):
        try:
            # Read 4-byte length prefix
            raw_msglen = self.recvall(conn, 4)
            if not raw_msglen: return
            msglen = struct.unpack('>I', raw_msglen)[0]
            
            # Read the full packet based on the prefix length
            data = self.recvall(conn, msglen)
            if not data: return
            
            packet = deserialize(data)
            if not packet: return

            msg_type = packet['type']
            payload = packet['payload']

            if msg_type == MSG_HELLO:
                self.node.add_peer(payload)
            elif msg_type == MSG_ONION:
                self._process_onion(payload)
            elif msg_type == MSG_DIRECT:
                mod = payload.get('module')
                content = payload.get('payload')
                if mod in self.node.modules:
                    self.node.modules[mod].receive(content)

        except Exception as e:
            print(f"Relay Error: {e}")
        finally:
            conn.close()

    def recvall(self, sock, n):
        """Helper to receive exactly n bytes to prevent fragmentation."""
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet: return None
            data.extend(packet)
        return data

    def _process_onion(self, encrypted_data):
        try:
            decrypted_bytes = hybrid_decrypt(encrypted_data, self.node.private_key)
            if decrypted_bytes is None: return

            layer_json = json.loads(decrypted_bytes.decode('utf-8'))
            inner_data = base64.b64decode(layer_json['data_b64'])
            next_hop = layer_json.get('next_hop')

            if next_hop is None:
                final_payload = json.loads(inner_data.decode('utf-8'))
                self.node.handle_exit_traffic(final_payload)
            else:
                host, port = next_hop
                self.node.send_raw(host, port, MSG_ONION, inner_data)
        except Exception as e:
            print(f"Onion Processing Error: {e}")