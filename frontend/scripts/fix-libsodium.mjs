// libsodium-wrappers' ESM build imports a relative "./libsodium.mjs" that
// the package never actually ships alongside it -- the real file lives in
// the separate `libsodium` package instead. Nothing in npm's install
// process bridges that gap, so every fresh `npm install` needs this copy
// re-applied (hence postinstall, not a one-time manual fix).
import { copyFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', 'node_modules', 'libsodium', 'dist', 'modules-esm', 'libsodium.mjs')
const dest = join(here, '..', 'node_modules', 'libsodium-wrappers', 'dist', 'modules-esm', 'libsodium.mjs')

if (existsSync(src)) {
  copyFileSync(src, dest)
  console.log('fix-libsodium: copied libsodium.mjs into libsodium-wrappers')
} else {
  console.warn('fix-libsodium: source file not found, skipping (libsodium-wrappers may not be installed)')
}
