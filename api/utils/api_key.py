import secrets
import hashlib

from datetime import datetime, timedelta, timezone
from typing import Optional


def parse_expiry_to_datetime(expiry: str) -> Optional[datetime]:
    """Convert expiry string (1H, 1D, 1M, 1Y) to datetime"""
    expiry = expiry.strip().upper()

    mapping = {
        "1H": timedelta(hours=1),
        "1D": timedelta(days=1),
        "1M": timedelta(days=30),
        "1Y": timedelta(days=365),
    }

    delta = mapping.get(expiry)
    if not delta:
        return None
    return datetime.now(timezone.utc) + delta


def generate_api_key() -> str:
    """Generate a random API key with prefix"""
    random_part = secrets.token_urlsafe(32)
    return f"sk_live__{random_part}"

def hash_api_key(api_key: str) -> str:
    """Hash API key for secure storage using SHA256"""
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify API key against hashed version"""
    return hashlib.sha256(plain_key.encode()).hexdigest() == hashed_key