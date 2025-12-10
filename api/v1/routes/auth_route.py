import os
import httpx
import secrets
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

load_dotenv()

oauth_state = secrets.token_urlsafe(16)

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo"
GOOGLE_SCOPES = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"


@router.get("/google")
async def google_login():
    """Redirect to Google OAuth"""
    oauth_params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/userinfo.profile openid https://www.googleapis.com/auth/userinfo.email",
        "access_type": "offline",
        "prompt": "consent",
        "state": oauth_state
    }
    authorization_url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(oauth_params)}"

    return success_response(
        status_code=200,
        message="Redirecting to Google OAuth",
        data={"authorization_url": authorization_url}
    )


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback and return JWT"""
    try:
        auth_code = request.query_params.get("code")
        if not auth_code:
            logger.warning("Missing authorization code in Google callback")
            return fail_response(
                status_code=400,
                message="Authorization code not found.",
                context={"error": "Missing authorization code"}
            )
        
        token_request_data = {
            "code": auth_code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }

        async with httpx.AsyncClient() as http_client:
            try:
                token_response = await http_client.post(GOOGLE_TOKEN_ENDPOINT, data=token_request_data)
                token_response.raise_for_status()
                token_data = token_response.json()
                access_token = token_data.get("access_token")
            except httpx.HTTPError as e:
                logger.exception("Failed to exchange authorization code for token")
                return fail_response(
                    status_code=400,
                    message="Failed to exchange authorization code for token.",
                    context={"error": str(e)}
                )
        
            try:
                auth_headers = {
                    "Authorization": f"Bearer {access_token}"
                }
                userinfo_response = await http_client.get(GOOGLE_USERINFO_ENDPOINT, headers=auth_headers)
                userinfo_response.raise_for_status()
                google_user_info = userinfo_response.json()
            except httpx.HTTPError as e:
                logger.exception("Failed to fetch user information from Google")
                return fail_response(
                    status_code=400,
                    message="Failed to fetch user information from Google.",
                    context={"error": str(e)}
                )
        
        user_email = google_user_info.get("email")
        google_user_id = google_user_info.get("id")
        user_full_name = google_user_info.get("name", user_email)

        if not user_email or not google_user_id:
            return fail_response(
                status_code=400,
                message="Invalid user information from Google.",
                context={"error": "Missing required fields (email or id)"}
            )

        try:
            user = User.fetch_one(db, google_id=google_user_id)

            if not user:
                user = User(
                    email=user_email,
                    full_name=user_full_name,
                    google_id=google_user_id
                )
                user.insert(db)

                user_wallet = Wallet(user_id=user.id)
                user_wallet.insert(db)
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
