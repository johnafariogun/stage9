from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.routes import auth_route, api_key_route, wallet_route

app = FastAPI(
    title="Wallet",
    description="It's a wallet",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
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
            "wallet": "/wallet/balance"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}