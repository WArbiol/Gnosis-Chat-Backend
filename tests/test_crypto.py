import pytest
from app.core.crypto import encrypt_message, decrypt_message, PREFIX


def test_encrypt_and_decrypt_roundtrip():
    user_id = "a1b2c3d4-e5f6-7890-1234-567890abcdef"
    original_text = "O Divino Daimon representa a parte superior do Ser íntimo. ✨📖"

    encrypted = encrypt_message(original_text, user_id)
    assert encrypted.startswith(PREFIX)
    assert encrypted != original_text

    decrypted = decrypt_message(encrypted, user_id)
    assert decrypted == original_text


def test_decrypt_with_wrong_user_id_fails_safely():
    user_1 = "user-1111-1111"
    user_2 = "user-2222-2222"
    original_text = "Segredo esotérico confidencial"

    encrypted = encrypt_message(original_text, user_1)
    
    # Decrypting with another user's key should safely fail (not raise exception, return cipher text)
    result = decrypt_message(encrypted, user_2)
    assert result != original_text


def test_legacy_plaintext_passthrough():
    user_id = "user-123"
    plain_legacy = "Mensagem antiga gravada antes da criptografia"

    # Does not start with PREFIX, should return plain text untouched
    assert decrypt_message(plain_legacy, user_id) == plain_legacy


def test_empty_and_none_handling():
    assert encrypt_message("", "user-123") == ""
    assert encrypt_message("test", None) == "test"
    assert decrypt_message("", "user-123") == ""
    assert decrypt_message(None, "user-123") is None
