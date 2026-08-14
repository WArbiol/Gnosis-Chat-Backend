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


def test_idempotency_does_not_double_encrypt():
    user_id = "user-123"
    text = "Texto sagrado gnóstico"
    
    encrypted_once = encrypt_message(text, user_id)
    encrypted_twice = encrypt_message(encrypted_once, user_id)
    
    # Should not re-encrypt already encrypted payload
    assert encrypted_once == encrypted_twice
    assert decrypt_message(encrypted_twice, user_id) == text


def test_multiline_markdown_and_latex_roundtrip():
    user_id = "user-abc-123"
    complex_text = """### Tratado sobre a Kundalini
1. **O despertar do fogo sagrado**:
   $$E = mc^2$$
   * Trecho em grego: *Gnosis Kardias* (Γνῶσις)
   ```python
   def despertar():
       return "Luz"
   ```
> Citação: Pistis Sophia, Cap. 12
"""
    encrypted = encrypt_message(complex_text, user_id)
    assert encrypted.startswith(PREFIX)
    assert decrypt_message(encrypted, user_id) == complex_text


def test_corrupted_payload_fails_gracefully():
    user_id = "user-123"
    bad_payload_1 = f"{PREFIX}corruptedBase64Data:invalidIV"
    bad_payload_2 = f"{PREFIX}onlyOnePartWithoutColon"
    bad_payload_3 = f"{PREFIX}AAAA:BBBB:CCCC"

    # Should not crash or throw unhandled exceptions
    assert decrypt_message(bad_payload_1, user_id) == bad_payload_1
    assert decrypt_message(bad_payload_2, user_id) == bad_payload_2
    assert decrypt_message(bad_payload_3, user_id) == bad_payload_3


def test_large_content_encryption_roundtrip():
    user_id = "user-large-test"
    large_text = "Samael Aun Weor - O Matrimônio Perfeito.\n" * 1000  # ~40 KB

    encrypted = encrypt_message(large_text, user_id)
    assert encrypted.startswith(PREFIX)
    decrypted = decrypt_message(encrypted, user_id)
    assert decrypted == large_text
