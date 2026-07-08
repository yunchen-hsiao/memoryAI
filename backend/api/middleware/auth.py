"""
Authentication middleware for MemoryAI API.

Provides get_current_user FastAPI dependency used by all protected routes.
"""
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()

# Supabase client for auth validation
_supabase_url = os.environ.get("SUPABASE_URL")
_supabase_key = os.environ.get("SUPABASE_KEY")
_supabase: Client = create_client(_supabase_url, _supabase_key) if _supabase_url and _supabase_key else None


def get_supabase() -> Client:
    """FastAPI dependency that returns the Supabase client."""
    if _supabase is None:
        raise RuntimeError("Supabase client not initialized — check SUPABASE_URL and SUPABASE_KEY")
    return _supabase


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase: Client = Depends(get_supabase),
):
    """
    FastAPI dependency that validates the Bearer JWT token.

    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
    """
    token = credentials.credentials
    try:
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        return user_res.user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
