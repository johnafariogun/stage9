import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from api.db.database import get_db
from api.v1.models.api_key import APIKey
from api.v1.models.user import User
from api.utils.deps import get_authenticated_user
from api.utils.api_key import generate_api_key, hash_api_key, parse_expiry_to_datetime
from api.utils.responses import success_response, fail_response
from api.utils.logger import logger

router = APIRouter(prefix="/keys", tags=["API Keys"])


class CreateAPIKeyRequest(BaseModel):
    name: str
    permissions: List[str]
    expiry: str


class RolloverAPIKeyRequest(BaseModel):
    expired_key_id: str
    expiry: str


@router.post("/create")
async def create_api_key(
    request: CreateAPIKeyRequest,
    auth_data: tuple = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    """Create new API key for authenticated user"""
    try:
        user, _ = auth_data
        
        expires_at = parse_expiry_to_datetime(request.expiry)
        if not expires_at:
            return fail_response(
                status_code=400,
                message="Invalid expiry format",
                context={"valid_formats": "1H, 1D, 1M, or 1Y"}
            )
        
        active_keys = [
            key for key in APIKey.fetch_all(db, user_id=user.id)
            if key.is_active()
        ]
        
        if len(active_keys) >= 5:
            return fail_response(
                status_code=400,
                message="Maximum 5 active API keys allowed per user",
                context={"active_keys_count": len(active_keys)}
            )
        
        valid_permissions = ["deposit", "transfer", "read"]
        for perm in request.permissions:
            if perm not in valid_permissions:
                logger.warning("Invalid permission requested: %s", perm)
                return fail_response(
                    status_code=400,
                    message=f"Invalid permission: {perm}",
                    context={"valid_permissions": valid_permissions}
                )
        
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)
        
        api_key = APIKey(
            user_id=user.id,
            name=request.name,
            hashed_key=hashed_key,
            permissions=request.permissions,
            expires_at=expires_at,
            revoked=False
        )
        api_key.insert(db)
        
        return success_response(
            status_code=201,
            message="API key created successfully",
            data={
                "api_key": plain_key,
                "expires_at": expires_at.isoformat()
            }
        )
    except Exception as e:
        logger.exception("Failed to create API key for user")
        return fail_response(
            status_code=500,
            message="Failed to create API key",
            context={"error": str(e)}
        )


@router.post("/rollover")
async def rollover_api_key(
    request: RolloverAPIKeyRequest,
    auth_data: tuple = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    """Rollover an expired API key with new expiry"""
    try:
        user, _ = auth_data
        
        try:
            key_id = uuid.UUID(request.expired_key_id)
        except ValueError:
            logger.warning("Invalid UUID provided for rollover: %s", request.expired_key_id)
            return fail_response(
                status_code=400,
                message="Invalid key ID format",
                context={"error": "Key ID must be a valid UUID"}
            )
        
        old_key = APIKey.fetch_one(db, id=key_id, user_id=user.id)
        
        if not old_key:
            logger.info("API key not found for rollover: %s", str(key_id))
            return fail_response(
                status_code=404,
                message="API key not found",
                context={"key_id": str(key_id)}
            )
        
        if old_key.is_active():
            return fail_response(
                status_code=400,
                message="Cannot rollover active key. Key must be expired.",
                context={"expires_at": old_key.expires_at.isoformat()}
            )
        
        new_expires_at = parse_expiry_to_datetime(request.expiry)
        if not new_expires_at:
            return fail_response(
                status_code=400,
                message="Invalid expiry format",
                context={"valid_formats": "1H, 1D, 1M, or 1Y"}
            )
        
        # Check active key limit
        active_keys = [
            key for key in APIKey.fetch_all(db, user_id=user.id)
            if key.is_active()
        ]
        
        if len(active_keys) >= 5:
            return fail_response(
                status_code=400,
                message="Maximum 5 active API keys allowed per user",
                context={"active_keys_count": len(active_keys)}
            )
        
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)
        
        new_key = APIKey(
            user_id=user.id,
            name=old_key.name,
            hashed_key=hashed_key,
            permissions=old_key.permissions,
            expires_at=new_expires_at,
            revoked=False
        )
        new_key.insert(db)
        
        return success_response(
            status_code=201,
            message="API key rolled over successfully",
            data={
                "api_key": plain_key,
                "expires_at": new_expires_at.isoformat(),
                "permissions": old_key.permissions
            }
        )
    except Exception as e:
        logger.exception("Failed to rollover API key for user")
        return fail_response(
            status_code=500,
            message="Failed to rollover API key",
            context={"error": str(e)}
        )