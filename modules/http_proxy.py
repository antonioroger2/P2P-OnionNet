import threading
import uuid
import random
from urllib.parse import urlparse

import requests

from core.protocol import MSG_DIRECT

class ProxyModule:
    def __init__(self, node):
        self.node = node
        self.request_timeout = 20

        # request_id -> threading.Event
        self.pending_events = {}
        # request_id -> response payload
        self.pending_results = {}
        self._lock = threading.Lock()

    def fetch_url(self, target_url, timeout=None):
        timeout = timeout or self.request_timeout
        target_url = (target_url or "").strip()
        if not target_url:
            return {"ok": False, "error": "URL cannot be empty."}

        if not target_url.startswith(("http://", "https://")):
            target_url = f"http://{target_url}"

        parsed = urlparse(target_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"ok": False, "error": "Only valid http/https URLs are supported."}

        peers = list(self.node.peers.keys())
        if not peers:
            return {"ok": False, "error": "No peers available. Connect to at least one peer first."}

        request_id = uuid.uuid4().hex
        evt = threading.Event()
        with self._lock:
            self.pending_events[request_id] = evt

        exit_peer = random.choice(peers)
        self.node.send_onion_to_peer(exit_peer, "proxy", {
            "type": "web_fetch",
            "request_id": request_id,
            "url": target_url,
            "reply_to_fp": self.node.pub_key.decode("utf-8"),
            "reply_to_host": self.node.get_local_ip(),
            "reply_to_port": self.node.port,
        })

        if not evt.wait(timeout=timeout):
            with self._lock:
                self.pending_events.pop(request_id, None)
                self.pending_results.pop(request_id, None)
            return {"ok": False, "error": "Request timed out waiting for an exit node response."}

        with self._lock:
            response = self.pending_results.pop(request_id, None)
            self.pending_events.pop(request_id, None)

        if not response:
            return {"ok": False, "error": "No response payload received."}
        return response

    def receive(self, payload):
        """Handles web fetch requests (exit role) and replies (client role)."""
        msg_type = payload.get('type')
        request_id = payload.get('request_id')

        if msg_type == "web_fetch":
            threading.Thread(target=self._handle_web_fetch_as_exit, args=(payload,), daemon=True).start()
        elif msg_type == "web_fetch_reply" and request_id:
            with self._lock:
                self.pending_results[request_id] = payload
                evt = self.pending_events.get(request_id)
            if evt:
                evt.set()

    def _handle_web_fetch_as_exit(self, payload):
        request_id = payload.get("request_id")
        target_url = (payload.get("url") or "").strip()
        reply_payload = {
            "type": "web_fetch_reply",
            "request_id": request_id,
            "ok": False,
            "status_code": None,
            "html": "",
            "error": "Unknown error",
            "url": target_url,
        }

        if not target_url:
            reply_payload["error"] = "Missing target URL"
            self._send_fetch_reply(payload, reply_payload)
            return

        try:
            headers = {
                "User-Agent": "OnionNet-WebFetch/1.0"
            }
            resp = requests.get(target_url, timeout=12, headers=headers)
            reply_payload.update({
                "ok": True,
                "status_code": resp.status_code,
                "html": resp.text,
                "error": "",
            })
        except Exception as exc:
            reply_payload["error"] = str(exc)

        self._send_fetch_reply(payload, reply_payload)

    def _send_fetch_reply(self, request_payload, reply_payload):
        reply_fp = request_payload.get("reply_to_fp")
        reply_host = request_payload.get("reply_to_host")
        reply_port = request_payload.get("reply_to_port")

        target_peer = self._find_peer_by_key(reply_fp)
        if target_peer:
            self.node.send_onion_to_peer(target_peer, "proxy", reply_payload)
        elif reply_host and reply_port:
            self.node.send_raw(reply_host, int(reply_port), MSG_DIRECT, {
                "module": "proxy",
                "payload": reply_payload,
            })

    def _find_peer_by_key(self, target_pub_key_str):
        for pid, meta in self.node.peers.items():
            p_key = meta.get('pub_key')
            if isinstance(p_key, bytes): p_key = p_key.decode('utf-8')
            if p_key == target_pub_key_str: return pid
        return None

    def stop(self):
        with self._lock:
            for evt in self.pending_events.values():
                evt.set()
            self.pending_events.clear()
            self.pending_results.clear()