import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.credential_manager import CredentialManager


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def get_password(self, service, username):
        return self.store.get((service, username))

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


def test_save_account_moves_latest_profile_to_front(monkeypatch):
    fake_keyring = FakeKeyring()
    monkeypatch.setattr("config.credential_manager.keyring", fake_keyring)

    CredentialManager.save_account("binanceus_abc123", {"broker": {"exchange": "binanceus"}})
    CredentialManager.save_account("stellar_GD37VD", {"broker": {"exchange": "stellar"}})

    accounts = CredentialManager.list_accounts()

    assert accounts == ["stellar_GD37VD", "binanceus_abc123"]


def test_touch_account_promotes_existing_profile(monkeypatch):
    fake_keyring = FakeKeyring()
    monkeypatch.setattr("config.credential_manager.keyring", fake_keyring)

    CredentialManager.save_account("binanceus_abc123", {"broker": {"exchange": "binanceus"}})
    CredentialManager.save_account("stellar_GD37VD", {"broker": {"exchange": "stellar"}})
    CredentialManager.touch_account("binanceus_abc123")

    accounts = CredentialManager.list_accounts()

    assert accounts == ["binanceus_abc123", "stellar_GD37VD"]
