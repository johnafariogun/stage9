from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import os
import jwt
from datetime import datetime, timedelta, timezone


from api.db.database import get_db
from api.utils.api_key import verify_api_key
from api.v1.models.user import User
from api.v1.models.api_key import APIKey


from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "9999"))


def create_jwt_token(user_id: str, email: str) -> str:
    """Create JWT token for authenticated user"""
    payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_jwt_token(token: str) -> Optional[dict]:
    """verify and decode JWT token"""
    try :
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    

async def get_current_user_from_jwt(
        authorization: Optional[str] = Header(None),
        db: Session = Depends(get_db)
) -> Optional[User]:
    """Extract user from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    payload = verify_jwt_token(token)
    
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    user = User.fetch_one(db, id=uuid.UUID(user_id))
    return user


async def get_current_user_from_api_key(
        x_api_key: Optional[str] = Header(None),
        db: Session = Depends(get_db)
) -> Optional[User]:
    """Extract user and API key from x-api-key header"""
    if not x_api_key:
        return None
    
    api_keys = APIKey.fetch_all(db)

    for api_key in api_keys:
        if verify_api_key(x_api_key, api_key.hashed_key):
            if not api_key.is_active():
                raise HTTPException(status_code=401, detail="API key is revoked or expired")
            
            user = User.fetch_one(db, id=api_key.user_id)
            if not user:
                raise HTTPException(status_code=401, detail="User not found for the provided API key")
            return (user, api_key)
        
    return None


async def get_authenticated_user(
    jwt_user: Optional[User] = Depends(get_current_user_from_jwt),
    api_key_data: Optional[tuple] = Depends(get_current_user_from_api_key)
) -> tuple[User, Optional[APIKey]]:
    """
    Get authenticated user from either JWT or API key.
    Returns (User, APIKey or None)
    """
    if jwt_user:
        return (jwt_user, None)
    
    if api_key_data:
        return api_key_data
    
    raise HTTPException(status_code=401, detail="Authentication required")


def require_permission(permission: str):
    """Dependency to check API key permission"""
    async def permission_checker(
        auth_data: tuple = Depends(get_authenticated_user)
        ):
        user, api_key = auth_data

        #JWT users have all permissions
        if api_key is None:
            return user
        
        #api key users need permission check
        if permission not in api_key.permissions:
            raise HTTPException(status_code=403, detail="Insufficient API key permissions")
        return user
    return permission_checker

        

    