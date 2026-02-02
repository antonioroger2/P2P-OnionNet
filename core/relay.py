import socket
import threading
import json
import base64
from core.protocol import deserialize, MSG_HELLO, MSG_ONION, MSG_CHUNK, MSG_DIRECT
from core.crypto import hybrid_decrypt

class RelayService:
    def __init__(self, node):
        self.node = node
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = True

    def bind_and_listen(self, port_range, bind_ip='0.0.0.0'):
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
            data = conn.recv(1024 * 64) 
            if not data: return
            
            packet = deserialize(data)
            if not packet: return

            msg_type = packet['type']
            payload = packet['payload']

            if msg_type == MSG_HELLO:
                self.node.add_peer(payload)

            elif msg_type == MSG_ONION:
                self._process_onion(payload)

            elif msg_type == MSG_CHUNK:
                self.node.modules['torrent'].handle_chunk(payload)
            
            elif msg_type == MSG_DIRECT:
                mod = payload.get('module')
                content = payload.get('content')
                if mod in self.node.modules:
                    self.node.modules[mod].receive(content)

        except Exception as e:
            print(f"Relay Error: {e}")
        finally:
            conn.close()

    def _process_onion(self, encrypted_data):
        try:
            decrypted_bytes = hybrid_decrypt(encrypted_data, self.node.private_key)
            if decrypted_bytes is None: return

            layer_json = json.loads(decrypted_bytes.decode('utf-8'))
            # Fix: Properly handle double-encoding if it exists
            inner_data = base64.b64decode(layer_json['data_b64'])
            next_hop = layer_json.get('next_hop')

            if next_hop is None:
                # We are the Exit Node
                final_payload = json.loads(inner_data.decode('utf-8'))
                # Use thread-safe handling for modules
                self.node.handle_exit_traffic(final_payload)
            else:
                # We are a Middle Node
                host, port = next_hop
                self.node.send_raw(host, port, MSG_ONION, inner_data)
        except Exception as e:
            print(f"Relay Error: {e}")