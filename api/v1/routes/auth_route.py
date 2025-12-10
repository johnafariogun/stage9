import os
import httpx
from fastapi import APIRouter, Request, Depends
from urllib.parse import urlencode, quote
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from api.db.database import get_db
from api.v1.models.user import User
from api.v1.models.wallet import Wallet
from api.utils.deps import create_jwt_token
from api.utils.responses import success_response, fail_response
from api.utils.logger import logger
import secrets
state = secrets.token_urlsafe(16)
load_dotenv()

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo"
SCOPES = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"


@router.get("/google")
async def google_login():
    """Redirect to Google OAuth"""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/userinfo.profile openid https://www.googleapis.com/auth/userinfo.email",
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }
    url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    return success_response(
        status_code=200,
        message="Redirecting to Google OAuth",
        data={"authorization_url": url}
    )


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: Session = Depends(get_db)

):
    """Handle Google OAuth callback and return JWT"""
    try:
        code = request.query_params.get("code")
        if not code:
            logger.warning("Missing authorization code in Google callback")
            return fail_response(
                status_code=400,
                message="Authorization code not found.",
                context={"error": "Missing authorization code"}
            )
        
        data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }

        async with httpx.AsyncClient() as client:
            try:
                token_response = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)
                token_response.raise_for_status()
                tokens = token_response.json()
                access_token = tokens.get("access_token")
            except httpx.HTTPError as e:
                logger.exception("Failed to exchange authorization code for token")
                return fail_response(
                    status_code=400,
                    message="Failed to exchange authorization code for token.",
                    context={"error": str(e)}
                )
        
            try:
                headers = {
                    "Authorization": f"Bearer {access_token}"
                }
                userinfo_response = await client.get(GOOGLE_USERINFO_ENDPOINT, headers=headers)
                userinfo_response.raise_for_status()
                user_info = userinfo_response.json()
            except httpx.HTTPError as e:
                logger.exception("Failed to fetch user information from Google")
                return fail_response(
                    status_code=400,
                    message="Failed to fetch user information from Google.",
                    context={"error": str(e)}
                )
        
        email = user_info.get("email")
        google_id = user_info.get("id")
        full_name = user_info.get("name", email)

        if not email or not google_id:
            return fail_response(
                status_code=400,
                message="Invalid user information from Google.",
                context={"error": "Missing required fields (email or id)"}
            )

        try:
            user = User.fetch_one(db, google_id=google_id)

            if not user:
                user = User(
                    email=email,
                    full_name=full_name,
                    google_id=google_id
                )
                user.insert(db)

                wallet = Wallet(user_id=user.id)
                wallet.insert(db)
        except Exception as e:
            logger.exception("Failed to create or retrieve user")
            return fail_response(
                status_code=500,
                message="Failed to create or retrieve user.",
                context={"error": str(e)}
            )

        try:
            if not user.email:
                return fail_response(
                    status_code=500,
                    message="User email is not set.",
                    context={"error": "Missing user email"}
                )
            jwt_token = create_jwt_token(str(user.id), user.email)
        except Exception as e:
            logger.exception("Failed to create JWT token for user %s", getattr(user, 'id', None))
            return fail_response(
                status_code=500,
                message="Failed to create JWT token.",
                context={"error": str(e)}
            )

        logger.info("User authenticated successfully: %s", getattr(user, 'id', None))
        return success_response(
            status_code=200,
            message="Authentication successful",
            data={
                "jwt_token": jwt_token,
                "user": {
                    "id": str(user.id),
                    "full_name": user.full_name,
                    "email": user.email
                }
            }
        )
    
    except Exception as e:
        logger.exception("Unexpected error during Google authentication")
        return fail_response(
            status_code=500,
            message="An unexpected error occurred during authentication.",
            context={"error": str(e)}
        )
