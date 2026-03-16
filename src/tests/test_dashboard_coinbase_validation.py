import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.dashboard import Dashboard


def test_coinbase_validation_accepts_valid_pem_with_org_key_name():
    error = Dashboard._coinbase_validation_error(
        "organizations/test/apiKeys/key-1",
        "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIExamplePrivateKeyMaterial1234567890\n-----END EC PRIVATE KEY-----\n",
        password=None,
    )

    assert error is None


def test_coinbase_validation_rejects_non_advanced_trade_api_key_name():
    error = Dashboard._coinbase_validation_error(
        "GA4CIZX3QJADGZZKI7HUS6WVHBNIX3EUNUW4MZUDW7VR7UIFV6D4CQW4",
        "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIExamplePrivateKeyMaterial1234567890\n-----END EC PRIVATE KEY-----\n",
        password=None,
    )

    assert "must start with organizations/" in error


def test_coinbase_validation_rejects_truncated_private_key():
    error = Dashboard._coinbase_validation_error(
        "organizations/test/apiKeys/key-1",
        "H\\nM6aXBtEitse01mWyswFekSdYpm9s7nha3w==\\n-----END EC PRIVATE KEY-----",
        password=None,
    )

    assert "malformed" in error.lower()


def test_coinbase_validation_rejects_passphrase_usage():
    error = Dashboard._coinbase_validation_error(
        "organizations/test/apiKeys/key-1",
        "\"-----BEGIN EC PRIVATE KEY-----\\nMHcCAQEEIExamplePrivateKeyMaterial1234567890\\n-----END EC PRIVATE KEY-----\\n\"",
        password="legacy-passphrase",
    )

    assert "does not use the passphrase field" in error
