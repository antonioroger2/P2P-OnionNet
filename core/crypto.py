import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes

def generate_rsa_keypair():
    """Generates a secure RSA 2048-bit keypair."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()
    
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_key, pem_public

def hybrid_encrypt(data: bytes, public_key_pem: bytes) -> bytes:
    """
    Encrypts data using RSA-OAEP + AES-GCM (Authenticated Encryption).
    Structure: [Encrypted AES Key (256 bytes)] + [Nonce (12 bytes)] + [Ciphertext + Tag]
    """
    try:
        # 1. Generate AES-GCM-256 Key (32 bytes) and Nonce (12 bytes)
        aes_key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(aes_key)
        nonce = os.urandom(12)
        
        # 2. Encrypt Data (AES-GCM)
        # GCM handles integrity automatically (Tag is appended to ciphertext)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        
        # 3. Encrypt AES Key with Receiver's RSA Public Key
        if isinstance(public_key_pem, str):
            public_key_pem = public_key_pem.encode('utf-8')
        
        public_key = serialization.load_pem_public_key(public_key_pem)
        encrypted_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # 4. Combine: [RSA_Key (256)] + [Nonce (12)] + [Ciphertext]
        return encrypted_key + nonce + ciphertext
        
    except Exception as e:
        print(f"Encryption Error: {e}")
        return None

def hybrid_decrypt(payload: bytes, private_key) -> bytes:
    """
    Decrypts using RSA + AES-GCM.
    """
    try:
        # RSA 2048 Key Size = 256 bytes
        # AES-GCM Nonce = 12 bytes
        if len(payload) < 268: 
            return None

        encrypted_key = payload[:256]
        nonce = payload[256:268]
        ciphertext = payload[268:]
        
        # 1. Decrypt AES Key
        aes_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # 2. Decrypt Data (Verification happens here automatically)
        aesgcm = AESGCM(aes_key)
        return aesgcm.decrypt(nonce, ciphertext, None)
        
    except Exception as e:
        # Decryption fails if auth tag is invalid (Tamper Resistance)
        print(f"Decryption/Integrity Error: {e}")
        return None