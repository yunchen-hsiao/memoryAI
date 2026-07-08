"""
Backwards compatibility wrapper for encryption functions.

Use services.encryption_service directly in new code.
"""
from services.encryption_service import encrypt_text, decrypt_text

__all__ = ['encrypt_text', 'decrypt_text']
