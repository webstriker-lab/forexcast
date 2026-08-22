import sodium from 'libsodium-wrappers'

/**
 * Encrypts a message with libsodium's crypto_box_seal (anonymous sealed
 * box) so the backend's PyNaCl `SealedBox.decrypt()` can recover it --
 * see backend/app/agent/crypto.py. Both libsodium-wrappers (here) and
 * PyNaCl (backend) bind the same underlying libsodium C library, so
 * this is wire-compatible by construction: unlike a hand-rolled
 * "ephemeral keypair + nacl.box + transmitted nonce" scheme (which is
 * NOT the same format -- crypto_box_seal derives its nonce
 * deterministically from blake2b(ephemeral_pk || recipient_pk) and
 * never transmits one), this produces exactly
 * `ephemeral_public_key (32 bytes) || box_ciphertext`, the only shape
 * SealedBox.decrypt understands.
 *
 * `publicKeyBase64` is the recipient's public key (standard, padded
 * base64 -- matching Python's `base64.b64encode` output), and the
 * return value is standard base64 ciphertext ready to write into
 * `llm_settings.api_key_encrypted`.
 */
export async function sealBox(message: string, publicKeyBase64: string): Promise<string> {
  await sodium.ready
  const publicKey = sodium.from_base64(publicKeyBase64, sodium.base64_variants.ORIGINAL)
  const messageBytes = sodium.from_string(message)
  const sealed = sodium.crypto_box_seal(messageBytes, publicKey)
  return sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL)
}
