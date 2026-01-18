import threading
import time
import socket
from core.protocol import serialize, MSG_HELLO

class DiscoveryService:
    def __init__(self, node, port_range=range(6000, 6010)):
        self.node = node
        self.port_range = port_range
        self.running = True

    def start(self):
        threading.Thread(target=self._scan_loop, daemon=True).start()

    def _scan_loop(self):
        while self.running:
            # Broadcast HELLO to all ports in range on localhost
            for p in self.port_range:
                if p == self.node.port:
                    continue
                self._ping(p)
            time.sleep(10)  # Rescan every 10s

    def _ping(self, target_port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(('127.0.0.1', target_port))

            # Send Public Key/Identity
            payload = {
                "host": '127.0.0.1',
                "port": self.node.port,
                "pub_key": self.node.pub_key
            }
            s.send(serialize(MSG_HELLO, payload))
            s.close()
        except:
            pass
