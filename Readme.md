# OnionNet: Secure P2P Overlay Network

OnionNet is a decentralized, privacy-preserving overlay network engineered to provide anonymity and end-to-end confidentiality for peer-to-peer communication. Built on a custom implementation of onion routing, the system constructs dynamic multi-hop circuits where intermediate relays perform layered decryption, ensuring no single node possesses knowledge of both the sender and the destination.

## Core Architecture
* **Zero-Trust Routing:** Relays are treated as untrusted transport entities.
* **Layered Encryption:** Implements Hybrid Encryption using **RSA-2048** for key exchange and **AES-GCM** (Authenticated Encryption) for data payloads.
* **Traffic Analysis Resistance:** Multi-hop circuits obfuscate traffic sources.

## Modules
1.  **Onion Chat:** Anonymous CLI/Dashboard chat with encrypted message routing.
2.  **Artifact Swarm:** Encrypted, BitTorrent-style distributed file sharing with SHA-256 integrity verification.
3.  **Onion Proxy:** HTTP Exit node capability allowing anonymous web access.
4.  **Circuit Manager:** Dynamic path selection and layered packet construction.

## Usage
1.  Install dependencies: `pip install -r requirements.txt`
2.  Run the Node: `streamlit run app.py`
3.  Connect multiple instances to form a mesh.