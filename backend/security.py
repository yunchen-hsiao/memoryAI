import os
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError(
        "ENCRYPTION_KEY is required; refusing to start without application encryption"
    )

try:
    fernet = Fernet(ENCRYPTION_KEY.encode("utf-8"))
except Exception as error:
    raise RuntimeError("ENCRYPTION_KEY is invalid; expected a valid Fernet key") from error


def encrypt_text(text: str, user_email: str = "") -> str:
    """Encrypt text before persistence; never silently fall back to plaintext."""
    if not text:
        return text

    try:
        return fernet.encrypt(text.encode("utf-8")).decode("utf-8")
    except Exception as error:
        raise RuntimeError("Failed to encrypt sensitive text") from error


def decrypt_text(text: str) -> str:
    """
    Decrypt text using the configured key.

    InvalidToken is retained as a compatibility path for legacy plaintext rows. New writes
    never use this path; a later migration should convert or explicitly classify old rows.
    Other failures are raised instead of being silently returned as plaintext.
    """
    if not text:
        return text

    try:
        return fernet.decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # 相容既有尚未加密的舊資料；新資料一律由 encrypt_text() 加密。
        return text
    except Exception as error:
        raise RuntimeError("Failed to decrypt sensitive text") from error
