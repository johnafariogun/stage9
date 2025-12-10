import secrets
import hashlib

from datetime import datetime, timedelta, timezone
from typing import Optional
from .logger import logger


def parse_expiry_to_datetime(expiry_string: str) -> Optional[datetime]:
    """Convert expiry string (1H, 1D, 1M, 1Y) to datetime"""
    
    expiry_string = expiry_string.strip().upper()

    time_delta_mapping = {
        "1H": timedelta(hours=1),
        "1D": timedelta(days=1),
        "1M": timedelta(days=30),
        "1Y": timedelta(days=365),
    }

    time_delta = time_delta_mapping.get(expiry_string)
    if not time_delta:
        return None
    return datetime.now(timezone.utc) + time_delta


def generate_api_key() -> str:
    """Generate a random API key with prefix"""
    random_part = secrets.token_urlsafe(32)
    return f"sk_live__{random_part}"

def hash_api_key(api_key_string: str) -> str:
    """Hash API key for secure storage using SHA256"""
    logger.info("hashing api key")
    return hashlib.sha256(api_key_string.encode()).hexdigest()


def verify_api_key(plain_key_string: str, hashed_key_string: str) -> bool:
    """Verify API key against hashed version"""
    logger.info("parsing api key")
    return hashlib.sha256(plain_key_string.encode()).hexdigest() == hashed_key_string