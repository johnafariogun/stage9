from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.routes import auth_route, api_key_route, wallet_route
from fastapi import FastAPI
from fastapi.security import HTTPBearer, APIKeyHeader


bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="JWT token passed in the Authorization header as 'Bearer <token>'"
)

api_key_scheme = APIKeyHeader(
    name="X-Api-Key",
    description="API Key passed in the custom X-Api-Key header"
)

app = FastAPI(
    title="Wallet API",
    description="API for wallet and key management.",
    openapi_extra={
        "security": [
            {"BearerAuth": []},
            {"APIKeyAuth": []},
        ]
    }
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_route.router)
app.include_router(api_key_route.router)
app.include_router(wallet_route.router)


@app.get("/")
async def root():
    return {
        "message": "Wallet Service API",
        "version": "1.0.0",
        "endpoints": {
            "auth": "/auth/google",
            "api_keys": "/keys/create",
            "wallet": "/wallet/balance",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}