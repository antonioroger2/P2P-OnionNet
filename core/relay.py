import socket
import threading
import json
import base64
import struct # Required for length prefixing
from core.protocol import deserialize, MSG_HELLO, MSG_ONION, MSG_CHUNK, MSG_DIRECT
from core.crypto import hybrid_decrypt

class RelayService:
    def __init__(self, node):
        self.node = node
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = True

    def _handle(self, conn):
        try:
            # Read 4-byte length prefix to know how much data is coming
            raw_msglen = self.recvall(conn, 4)
            if not raw_msglen: return
            msglen = struct.unpack('>I', raw_msglen)[0]
            
            # Read the actual packet data based on length
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

            elif msg_type == MSG_CHUNK:
                # Direct chunk handling if not using onion routing
                self.node.modules['torrent'].receive(payload)

        except Exception as e:
            print(f"Relay Error: {e}")
        finally:
            conn.close()

    def recvall(self, sock, n):
        """Helper to receive exactly n bytes from a socket."""
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
                # We are the Exit Node - trigger the local module (torrent/chat/proxy)
                final_payload = json.loads(inner_data.decode('utf-8'))
                self.node.handle_exit_traffic(final_payload)
            else:
                # We are a Middle Node - forward to the next hop
                host, port = next_hop
                self.node.send_raw(host, port, MSG_ONION, inner_data)
        except Exception as e:
            print(f"Relay Error: {e}")