from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional, Tuple
import uuid
import os
import jwt
from datetime import datetime, timedelta, timezone


from api.db.database import get_db
from .api_key import verify_api_key
from .logger import logger
from api.v1.models.user import User
from api.v1.models.api_key import APIKey


from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "9999"))


def create_jwt_token(user_id: str, email: str) -> str:
    """Create JWT token for authenticated user"""
    token_payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=EXPIRATION_MINUTES),
    }
    logger.info("Creating JWT token for user_id: %s", user_id)
    return jwt.encode(token_payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_jwt_token(token: str) -> Optional[dict]:
    """verify and decode JWT token"""
    try :
        token_payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.info("JWT token verified successfully. User sub: %s", token_payload.get("sub"))
        return token_payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid JWT token provided")
        return None

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_from_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    logger.debug("Attempting JWT authentication...")

    if not credentials:
        logger.debug("Missing Bearer token in authorization header")
        return None

    # Extract raw JWT string
    jwt_token = credentials.credentials

    token_payload = verify_jwt_token(jwt_token)

    if not token_payload:
        logger.warning("JWT token verification failed or expired")
        return None

    user_id_str = token_payload.get("sub")
    if not user_id_str:
        logger.warning("No 'sub' found in JWT payload.")
        return None

    try:
        parsed_user_id = uuid.UUID(user_id_str)
    except ValueError:
        logger.error(f"Invalid UUID in token: {user_id_str}")
        return None

    jwt_user = User.fetch_one(db, id=parsed_user_id)

    if jwt_user:
        logger.info(f"User authenticated: {parsed_user_id}")
    else:
        logger.warning(f"User not found for ID: {parsed_user_id}")

    return jwt_user


async def get_current_user_from_api_key(
        x_api_key: Optional[str] = Header(None, alias="x-api-key"),
        db: Session = Depends(get_db)
) -> Optional[Tuple[User, APIKey]]:
    """Extract user and API key from x-api-key header"""
    logger.debug("Attempting API Key authentication...")
    if not x_api_key:
        logger.debug("No API key provided in x-api-key header")
        return None
    
    all_api_keys = APIKey.fetch_all(db)

    for stored_api_key in all_api_keys:
        if verify_api_key(x_api_key, stored_api_key.hashed_key):
            logger.debug("API Key hash matched: %s", stored_api_key.id)
            if not stored_api_key.is_active():
                logger.warning("API key is revoked or expired: %s", stored_api_key.id)
                raise HTTPException(status_code=401, detail="API key is revoked or expired")
            
            key_user = User.fetch_one(db, id=stored_api_key.user_id)
            if not key_user:
                logger.error("User not found for API key: %s", stored_api_key.id)
                raise HTTPException(status_code=401, detail="User not found for the provided API key")
            
            logger.info("User authenticated via API key: %s", stored_api_key.id)
            return (key_user, stored_api_key)
        
    logger.warning("Invalid API key provided (hash not matched)")
    return None


async def get_authenticated_user(
    jwt_user: Optional[User] = Depends(get_current_user_from_jwt),
    api_key_auth_data: Optional[Tuple[User, APIKey]] = Depends(get_current_user_from_api_key)
) -> Tuple[User, Optional[APIKey]]:
    """
    Get authenticated user from either JWT or API key.
    Returns (User, APIKey or None)
    """
    if jwt_user:
        logger.debug("Authentication successful via JWT")
        return (jwt_user, None)
    
    if api_key_auth_data:
        logger.debug("Authentication successful via API Key")
        return api_key_auth_data
    
    logger.error("Authentication failed: Neither JWT nor API Key provided/valid.")
    raise HTTPException(status_code=401, detail="Authentication required")


def require_permission(required_permission: str):
    """Dependency to check API key permission"""
    async def permission_checker(
        auth_data: Tuple[User, Optional[APIKey]] = Depends(get_authenticated_user)
        ) -> User:
        authenticated_user, auth_api_key = auth_data

        if auth_api_key is None:
            logger.info("JWT user accessing resource with permission: %s", required_permission)
            return authenticated_user
        
        if required_permission not in auth_api_key.permissions:
            logger.warning("API key %s denied access due to missing permission: %s", auth_api_key.id, required_permission)
            raise HTTPException(status_code=403, detail="Insufficient API key permissions")
        
        logger.info("API key %s granted access with permission: %s", auth_api_key.id, required_permission)
        return authenticated_user
        
    return permission_checker