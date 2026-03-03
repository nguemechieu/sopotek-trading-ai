import keyring


class CredentialManager:

    SERVICE_NAME = "SopotekTradingApp"

    @staticmethod
    def save_credentials(exchange, api_key, secret):

        keyring.set_password(
            CredentialManager.SERVICE_NAME,
            f"{exchange}_api_key",
            api_key
        )

        keyring.set_password(
            CredentialManager.SERVICE_NAME,
            f"{exchange}_secret",
            secret
        )

    @staticmethod
    def load_credentials(exchange):

        api_key = keyring.get_password(
            CredentialManager.SERVICE_NAME,
            f"{exchange}_api_key"
        )

        secret = keyring.get_password(
            CredentialManager.SERVICE_NAME,
            f"{exchange}_secret"
        )

        return api_key, secret

    @staticmethod
    def delete_credentials(exchange):

        try:
            keyring.delete_password(
                CredentialManager.SERVICE_NAME,
                f"{exchange}_api_key"
            )
            keyring.delete_password(
                CredentialManager.SERVICE_NAME,
                f"{exchange}_secret"
            )
        except Exception:
            pass