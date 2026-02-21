import base64
import json
from typing import Any

# Packet Constants
MSG_HELLO = "HELLO"         # Discovery (Key Exchange)
MSG_ONION = "ONION_MSG"     # Routed Traffic (Encrypted)
MSG_CHUNK = "FILE_CHUNK"    # Torrent/File (Direct P2P)
MSG_DIRECT = "DIRECT"       # Direct Response (e.g., from Exit Node)

def serialize(packet_type: str, payload: Any) -> bytes:
    """
    Serializes packet to JSON bytes.
    Recursively encodes bytes to Base64 strings for JSON compatibility.
    """
    def encode_helper(item: Any) -> Any:
        if isinstance(item, bytes):
            return {'__bytes__': base64.b64encode(item).decode('utf-8')}
        elif isinstance(item, dict):
            return {k: encode_helper(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [encode_helper(i) for i in item]
        return item

    data = {
        "type": packet_type, 
        "payload": encode_helper(payload)
    }
    return json.dumps(data, separators=(",", ":")).encode("utf-8")

def deserialize(data_bytes: bytes):
    """
    Parses JSON bytes back to Python objects.
    Recursively decodes Base64 strings back to bytes.
    """
    def decode_helper(item: Any) -> Any:
        if isinstance(item, dict) and '__bytes__' in item:
            return base64.b64decode(item['__bytes__'])
        elif isinstance(item, dict):
            return {k: decode_helper(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [decode_helper(i) for i in item]
        return item

    try:
        if not isinstance(data_bytes, (bytes, bytearray)):
            return None

        data_str = bytes(data_bytes).decode('utf-8')
        packet = json.loads(data_str)

        if not isinstance(packet, dict):
            return None
        if 'type' not in packet or 'payload' not in packet:
            return None

        packet['payload'] = decode_helper(packet['payload'])
        return packet
    except Exception as e:
        print(f"Protocol Error (Deserialize): {e}")
        return None
