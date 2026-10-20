from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class PayPalVaultConfigurationError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().paypal_vault_encryption_key
    if not key:
        raise PayPalVaultConfigurationError(
            "Set PAYPAL_VAULT_ENCRYPTION_KEY before connecting a PayPal wallet."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise PayPalVaultConfigurationError(
            "PAYPAL_VAULT_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def assert_vault_encryption_ready() -> None:
    _fernet()


def encrypt_payment_token(token_id: str) -> str:
    if not token_id:
        raise ValueError("A PayPal payment token ID is required.")
    return _fernet().encrypt(token_id.encode("utf-8")).decode("utf-8")


def decrypt_payment_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise PayPalVaultConfigurationError(
            "The saved PayPal wallet cannot be decrypted. Check the vault encryption key and reconnect the wallet."
        ) from exc
