"""Unit tests for Windows Credential Manager integration."""

from unittest.mock import MagicMock, patch
import pytest
from src.publisher.services.credential_manager import CredentialManager


def test_credential_manager_flow():
    """Verify storing, checking presence, masking, and deleting credentials."""
    vault: dict[str, str] = {}

    def mock_set(service, key, value):
        vault[f"{service}:{key}"] = value

    def mock_get(service, key):
        return vault.get(f"{service}:{key}")

    def mock_del(service, key):
        vault.pop(f"{service}:{key}", None)

    manager = CredentialManager(service_name="TestPublisher")

    with patch("keyring.set_password", side_effect=mock_set):
        with patch("keyring.get_password", side_effect=mock_get):
            with patch("keyring.delete_password", side_effect=mock_del):
                # 1. Initially empty
                assert manager.has_credential("ai_api_key") is False
                assert manager.get_credential("ai_api_key") is None
                assert manager.get_masked_credential("ai_api_key") == ""

                # 2. Store secret
                success = manager.set_credential("ai_api_key", "sk-1234567890abcdef")
                assert success is True
                assert manager.has_credential("ai_api_key") is True
                assert manager.get_credential("ai_api_key") == "sk-1234567890abcdef"

                # 3. Masked display never reveals full secret
                masked = manager.get_masked_credential("ai_api_key", show_last=4)
                assert masked.endswith("cdef")
                assert "sk-12345" not in masked
                assert "•" in masked

                # 4. Deletion
                deleted = manager.delete_credential("ai_api_key")
                assert deleted is True
                assert manager.has_credential("ai_api_key") is False


def test_credential_manager_dpapi_persistence_recovery(tmp_path):
    """Verify secrets persist and recover across restarts even if keyring returns None."""
    store_file = tmp_path / ".secrets.enc"
    manager1 = CredentialManager(service_name="RestartTestService", store_path=store_file)

    # Save credential in first run
    with patch("keyring.set_password") as mock_set:
        saved = manager1.set_credential("github_pat", "ghp_secure_restart_token_98765")
        assert saved is True
        assert store_file.exists()

    # Simulate restart in a new process instance with keyring returning None
    manager2 = CredentialManager(service_name="RestartTestService", store_path=store_file)
    with patch("keyring.get_password", return_value=None), patch("keyring.set_password") as mock_heal:
        recovered = manager2.get_credential("github_pat")
        assert recovered == "ghp_secure_restart_token_98765"
        # Verify self-healing into keyring
        mock_heal.assert_called_with("RestartTestService", "github_pat", "ghp_secure_restart_token_98765")

