import base64

from nacl.public import PrivateKey, SealedBox

from app.config import get_settings


def decrypt_api_key(ciphertext_b64: str) -> str:
    """Decrypts a PyNaCl sealed-box-encrypted API key. The (future)
    frontend encrypts with the public half of this keypair -- baked
    into its build config, not secret -- before writing to
    llm_settings.api_key_encrypted; only this function, holding the
    private half via Settings.llm_settings_private_key, can recover the
    plaintext. The plaintext never touches any table or log; it exists
    only in memory for the duration of one chat request.

    Raises ValueError if the private key isn't configured, or if
    decryption fails (corrupted ciphertext, or ciphertext sealed with a
    different keypair) -- both are configuration/integrity problems,
    not normal-operation branches.
    """
    settings = get_settings()
    if not settings.llm_settings_private_key:
        raise ValueError("LLM_SETTINGS_PRIVATE_KEY is not configured")
    try:
        private_key = PrivateKey(base64.b64decode(settings.llm_settings_private_key))
        box = SealedBox(private_key)
        plaintext = box.decrypt(base64.b64decode(ciphertext_b64))
    except Exception as exc:
        raise ValueError(f"failed to decrypt API key: {exc}") from exc
    return plaintext.decode("utf-8")
