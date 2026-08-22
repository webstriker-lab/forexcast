import base64
from unittest.mock import MagicMock, patch

from nacl.public import PrivateKey, PublicKey, SealedBox

from app.agent.crypto import decrypt_api_key


def _encrypt_with(public_key: PublicKey, plaintext: str) -> str:
    box = SealedBox(public_key)
    return base64.b64encode(box.encrypt(plaintext.encode("utf-8"))).decode("ascii")


def test_decrypt_api_key_recovers_the_original_plaintext():
    private_key = PrivateKey.generate()
    ciphertext_b64 = _encrypt_with(private_key.public_key, "sk-test-12345")

    with patch("app.agent.crypto.get_settings") as mock_settings:
        mock_settings.return_value.llm_settings_private_key = base64.b64encode(
            bytes(private_key)
        ).decode("ascii")
        result = decrypt_api_key(ciphertext_b64)

    assert result == "sk-test-12345"


def test_decrypt_api_key_raises_when_private_key_not_configured():
    with patch("app.agent.crypto.get_settings") as mock_settings:
        mock_settings.return_value.llm_settings_private_key = ""
        try:
            decrypt_api_key("anything")
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "not configured" in str(exc)


def test_decrypt_api_key_raises_on_corrupted_ciphertext():
    private_key = PrivateKey.generate()
    with patch("app.agent.crypto.get_settings") as mock_settings:
        mock_settings.return_value.llm_settings_private_key = base64.b64encode(
            bytes(private_key)
        ).decode("ascii")
        try:
            decrypt_api_key(base64.b64encode(b"not a real sealed box").decode("ascii"))
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "failed to decrypt" in str(exc)


def test_decrypt_api_key_raises_when_ciphertext_was_sealed_with_a_different_keypair():
    correct_key = PrivateKey.generate()
    wrong_key = PrivateKey.generate()
    ciphertext_b64 = _encrypt_with(wrong_key.public_key, "sk-test-12345")

    with patch("app.agent.crypto.get_settings") as mock_settings:
        mock_settings.return_value.llm_settings_private_key = base64.b64encode(
            bytes(correct_key)
        ).decode("ascii")
        try:
            decrypt_api_key(ciphertext_b64)
            assert False, "expected ValueError"
        except ValueError:
            pass
