# ADR 0002: SQLCipher with a Keychain-held raw key

**Status:** accepted

**Decision.** Use SQLCipher through `sqlcipher3-wheels` (prebuilt, no system library
needed). The key is 32 random bytes stored in the macOS Keychain via `keyring`, supplied as a
raw key so no passphrase KDF runs per connection. Connections are opened per request.

**Fallback.** Plain SQLite only with `LOCALLEDGER_INSECURE_DEV_DB=1`, in a differently named
file, with a permanent warning in the UI. Never automatic.

**Consequences.** Losing the Keychain item makes the database unrecoverable. No user
password is needed. Key rotation and export are future work.
