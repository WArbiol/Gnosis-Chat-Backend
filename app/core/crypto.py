import base64
import hashlib
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

PEPPER = "GnosisSecretPepper2026"
PREFIX = "enc:v1:"


def _derive_key(user_id: str) -> bytes:
    """Derive a deterministic 256-bit AES key from user_id and app pepper."""
    return hashlib.sha256(f"{user_id}:{PEPPER}".encode("utf-8")).digest()


def encrypt_message(plain_text: str, user_id: str | None) -> str:
    """Encrypt message content for Supabase storage using user-derived AES-256."""
    if not plain_text or not user_id:
        return plain_text

    if plain_text.startswith(PREFIX):
        return plain_text

    try:
        key = _derive_key(str(user_id))
        iv = os.urandom(16)

        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plain_text.encode("utf-8")) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(padded_data) + encryptor.finalize()

        ct_b64 = base64.b64encode(ct).decode("utf-8")
        iv_b64 = base64.b64encode(iv).decode("utf-8")

        return f"{PREFIX}{ct_b64}:{iv_b64}"
    except Exception:
        return plain_text


def decrypt_message(cipher_text: str, user_id: str | None) -> str:
    """Decrypt message content retrieved from Supabase."""
    if not cipher_text or not isinstance(cipher_text, str) or not cipher_text.startswith(PREFIX) or not user_id:
        return cipher_text

    try:
        payload = cipher_text[len(PREFIX):]
        parts = payload.split(":")
        if len(parts) != 2:
            return cipher_text

        ct_b64, iv_b64 = parts
        key = _derive_key(str(user_id))
        iv = base64.b64decode(iv_b64)
        ct = base64.b64decode(ct_b64)

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ct) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        plain_bytes = unpadder.update(padded_data) + unpadder.finalize()

        return plain_bytes.decode("utf-8")
    except Exception:
        return cipher_text
