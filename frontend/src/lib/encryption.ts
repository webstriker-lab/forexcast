import nacl from 'tweetnacl'
import { decodeBase64, encodeBase64 } from 'tweetnacl-util'

/**
 * Encrypts a message using NaCl box with an ephemeral keypair.
 * This simulates sealed-box encryption: the sender generates a
 * one-time keypair, encrypts, and discards the secret key.
 * The public key is the server's LLM_SETTINGS_PUBLIC_KEY (base64).
 * Returns the ciphertext (ephemeral pubkey + nonce + box) as base64.
 */
export function sealBox(message: string, publicKeyBase64: string): string {
  const pubKey = decodeBase64(publicKeyBase64)
  const ephemeral = nacl.box.keyPair()
  const nonce = nacl.randomBytes(nacl.box.nonceLength)
  const messageBytes = new TextEncoder().encode(message)
  const sealed = nacl.box(messageBytes, nonce, pubKey, ephemeral.secretKey)
  // Prepend ephemeral public key + nonce to ciphertext
  const combined = new Uint8Array(ephemeral.publicKey.length + nonce.length + sealed.length)
  combined.set(ephemeral.publicKey)
  combined.set(nonce, ephemeral.publicKey.length)
  combined.set(sealed, ephemeral.publicKey.length + nonce.length)
  return encodeBase64(combined)
}
