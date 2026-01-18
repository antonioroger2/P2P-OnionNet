import json
import base64

# Packet Constants
MSG_HELLO = "HELLO"         # Discovery (Key Exchange)
MSG_ONION = "ONION_MSG"     # Routed Traffic (Encrypted)
MSG_CHUNK = "FILE_CHUNK"    # Torrent/File (Direct P2P)
MSG_DIRECT = "DIRECT"       # Direct Response (e.g., from Exit Node)

def serialize(packet_type, payload):
    """
    Serializes packet to JSON bytes.
    Recursively encodes bytes to Base64 strings for JSON compatibility.
    """
    def encode_helper(item):
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
    return json.dumps(data).encode('utf-8')

def deserialize(data_bytes):
    """
    Parses JSON bytes back to Python objects.
    Recursively decodes Base64 strings back to bytes.
    """
    def decode_helper(item):
        if isinstance(item, dict) and '__bytes__' in item:
            return base64.b64decode(item['__bytes__'])
        elif isinstance(item, dict):
            return {k: decode_helper(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [decode_helper(i) for i in item]
        return item

    try:
        data_str = data_bytes.decode('utf-8')
        packet = json.loads(data_str)
        packet['payload'] = decode_helper(packet['payload'])
        return packet
    except Exception as e:
        print(f"Protocol Error (Deserialize): {e}")
        return None