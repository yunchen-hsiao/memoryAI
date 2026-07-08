"""
Encryption service using Fernet symmetric encryption.

All sensitive text fields are encrypted before storage unless the user is an admin.
"""
import os
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

if ENCRYPTION_KEY:
    try:
        fernet = Fernet(ENCRYPTION_KEY.encode('utf-8'))
    except Exception as e:
        print(f"Warning: Failed to initialize Fernet with provided key: {e}")
        fernet = None
else:
    fernet = None


def encrypt_text(text: str, user_email: str) -> str:
    """
    Encrypts text unless the user is the admin.
    Returns the original text if no encryption key is set or text is empty.
    """
    if not text:
        return text
        
    # 如果發文者是管理員，直接存明文
    if ADMIN_EMAIL and user_email == ADMIN_EMAIL:
        return text
        
    if fernet is None:
        return text
        
    try:
        # Encrypt and return as string
        encrypted_bytes = fernet.encrypt(text.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        print(f"Encryption error: {e}")
        return text


def decrypt_text(text: str) -> str:
    """
    Decrypts text if it is encrypted.
    If decryption fails (e.g., old plaintext data or admin data), returns the original text.
    """
    if not text:
        return text
        
    if fernet is None:
        return text
        
    try:
        # Attempt to decrypt
        decrypted_bytes = fernet.decrypt(text.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        # If it throws InvalidToken, it means the text is likely plaintext (not encrypted by this key)
        return text
    except Exception as e:
        # For any other error, fallback to original text to prevent breaking the app
        return text
