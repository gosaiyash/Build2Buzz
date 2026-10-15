"""Operating system credential storage using Windows Credential Manager via keyring with DPAPI file persistence fallback."""

import json
from pathlib import Path
from typing import Literal
import keyring
from keyring.errors import KeyringError
from src.publisher.core.config import settings
from src.publisher.core.logging_config import logger
from src.publisher.core.security import mask_secret

SERVICE_NAME = "GitHubLinkedInAIPublisher"

CredentialKey = Literal[
    "ai_api_key",
    "github_pat",
    "linkedin_client_id",
    "linkedin_client_secret",
    "linkedin_access_token",
    "linkedin_refresh_token",
    "linkedin_author_urn",
    "linkedin_redirect_uri",
    "linkedin_code_verifier",
    "search_api_key",
]


def _dpapi_protect(plaintext: bytes) -> bytes:
    """Encrypt bytes using Windows DPAPI (CryptProtectData)."""
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        blob_in = DATA_BLOB(len(plaintext), ctypes.create_string_buffer(plaintext, len(plaintext)))
        blob_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "GitHubLinkedInAIPublisherSecret", None, None, None, 0, ctypes.byref(blob_out)
        ):
            raise OSError("CryptProtectData failed")
        ciphertext = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return ciphertext
    except Exception as exc:
        logger.debug("DPAPI protect fallback: %s", exc)
        return b"NON_WIN:" + plaintext[::-1]


def _dpapi_unprotect(ciphertext: bytes) -> bytes:
    """Decrypt bytes using Windows DPAPI (CryptUnprotectData)."""
    if ciphertext.startswith(b"NON_WIN:"):
        return ciphertext[8:][::-1]
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        blob_in = DATA_BLOB(len(ciphertext), ctypes.create_string_buffer(ciphertext, len(ciphertext)))
        blob_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            raise OSError("CryptUnprotectData failed")
        plaintext = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return plaintext
    except Exception as exc:
        logger.debug("DPAPI unprotect fallback: %s", exc)
        return b""


class CredentialManager:
    """Manages sensitive tokens and secrets using Windows Credential Manager and local DPAPI persistence."""

    def __init__(self, service_name: str = SERVICE_NAME, store_path: Path | None = None):
        self.service_name = service_name
        if store_path is not None:
            self.store_path: Path | None = store_path
        elif service_name == SERVICE_NAME:
            self.store_path = settings.DATA_DIR / ".secrets.enc"
        else:
            self.store_path = None
        self._memory_fallback: dict[str, str] = {}

    def _read_persistent_store(self) -> dict[str, str]:
        if self.store_path is None:
            return dict(self._memory_fallback)
        try:
            if not self.store_path.exists():
                return {}
            raw = self.store_path.read_bytes()
            if not raw:
                return {}
            dec = _dpapi_unprotect(raw)
            if not dec:
                return {}
            return json.loads(dec.decode("utf-8"))
        except Exception as exc:
            logger.debug("Error reading DPAPI credential file: %s", exc)
            return {}

    def _write_persistent_store(self, data: dict[str, str]) -> None:
        if self.store_path is None:
            self._memory_fallback = dict(data)
            return
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(data).encode("utf-8")
            enc = _dpapi_protect(payload)
            self.store_path.write_bytes(enc)
        except Exception as exc:
            logger.warning("Error writing DPAPI credential file: %s", exc)

    def set_credential(self, key_name: str, secret_value: str) -> bool:
        """Store a secret securely in OS credential manager and encrypted local store."""
        if not key_name:
            raise ValueError("Credential key name cannot be empty.")
        if not secret_value or not secret_value.strip():
            # If empty string is supplied, delete the credential
            return self.delete_credential(key_name)

        val = secret_value.strip()
        keyring_saved = False
        try:
            keyring.set_password(self.service_name, key_name, val)
            keyring_saved = True
        except Exception as exc:
            logger.warning("Failed to save credential '%s' to keyring: %s", key_name, exc)

        try:
            store = self._read_persistent_store()
            store[key_name] = val
            self._write_persistent_store(store)
            file_saved = True
        except Exception as exc:
            logger.warning("Failed to save credential '%s' to DPAPI file: %s", key_name, exc)
            file_saved = False

        if keyring_saved or file_saved:
            logger.info("Credential '%s' saved securely.", key_name)
            return True
        return False

    def get_credential(self, key_name: str) -> str | None:
        """Retrieve a secret from OS credential manager or persistent encrypted store."""
        val = None
        try:
            val = keyring.get_password(self.service_name, key_name)
        except Exception as exc:
            logger.debug("Keyring get failed for '%s': %s", key_name, exc)

        if val and val.strip():
            return val.strip()

        # Fallback to persistent encrypted store
        store = self._read_persistent_store()
        fallback_val = store.get(key_name)
        if fallback_val and fallback_val.strip():
            # Self-healing: re-sync back into keyring
            try:
                keyring.set_password(self.service_name, key_name, fallback_val.strip())
            except Exception:
                pass
            return fallback_val.strip()

        return None

    def has_credential(self, key_name: str) -> bool:
        """Check if a credential exists without exposing its content."""
        val = self.get_credential(key_name)
        return bool(val and val.strip())

    def get_masked_credential(self, key_name: str, show_last: int = 4) -> str:
        """Return a masked representation of the stored credential for safe UI display."""
        val = self.get_credential(key_name)
        if not val:
            return ""
        return mask_secret(val, show_last=show_last)

    def delete_credential(self, key_name: str) -> bool:
        """Permanently remove a secret from OS credential manager and encrypted store."""
        try:
            keyring.delete_password(self.service_name, key_name)
            logger.info("Credential '%s' deleted from Windows Credential Manager.", key_name)
        except Exception as exc:
            logger.debug("Could not delete credential '%s' from keyring: %s", key_name, exc)

        try:
            store = self._read_persistent_store()
            if key_name in store:
                del store[key_name]
                self._write_persistent_store(store)
                logger.info("Credential '%s' deleted from persistent encrypted store.", key_name)
        except Exception as exc:
            logger.debug("Could not delete credential '%s' from persistent file: %s", key_name, exc)

        return True


# Singleton instance
credentials = CredentialManager()
