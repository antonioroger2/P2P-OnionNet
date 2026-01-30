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

    def manual_connect(self, host, port):
        threading.Thread(target=self._ping, args=(host, int(port)), daemon=True).start()

    def _scan_loop(self):
        while self.running:
            for p in self.port_range:
                if p == self.node.port:
                    continue
                self._ping('127.0.0.1', p)
            time.sleep(10)

    def _ping(self, host, target_port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((host, target_port))

            advertised_host = self.node.get_local_ip()

            payload = {
                "host": advertised_host,
                "port": self.node.port,
                "pub_key": self.node.pub_key
            }
            s.send(serialize(MSG_HELLO, payload))
            s.close()
        except:
            pass