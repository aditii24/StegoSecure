import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import os

def generate_rsa_keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv_pem, pub_pem

def aes_encrypt(plaintext: str):
    key = AESGCM.generate_key(bit_length=128)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(ct).decode(), base64.b64encode(nonce).decode(), key

def aes_decrypt(ciphertext_b64: str, nonce_b64: str, key: bytes):
    aesgcm = AESGCM(key)
    ct = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode()

def rsa_wrap_key(aes_key: bytes, recipient_pub_pem: str) -> str:
    pub = serialization.load_pem_public_key(recipient_pub_pem.encode(), backend=default_backend())
    wrapped = pub.encrypt(
        aes_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None)
    )
    return base64.b64encode(wrapped).decode()

def rsa_unwrap_key(wrapped_b64: str, recipient_priv_pem: str) -> bytes:
    priv = serialization.load_pem_private_key(recipient_priv_pem.encode(), password=None, backend=default_backend())
    wrapped = base64.b64decode(wrapped_b64)
    key = priv.decrypt(
        wrapped,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None)
    )
    return key
