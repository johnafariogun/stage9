import os
import httpx
import hmac
import hashlib
from dotenv import load_dotenv
from api.utils.logger import logger

load_dotenv()

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"


async def initialize_transaction(email: str, amount: int, reference:str) -> dict:
    """Initiate a Paystack transaction
    Amount should be in kobo for NGN currency"""
    url = f"{PAYSTACK_BASE_URL}/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": email,
        "amount": amount,
        "reference": reference
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info("Initializing Paystack transaction for email: %s, amount: %s, reference: %s", email, amount, reference)
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info("Paystack transaction initialized successfully: %s", reference)
            return response.json()
    except httpx.HTTPError as e:
        logger.exception("Failed to initialize Paystack transaction for reference: %s", reference)
        raise
    

async def verify_transaction(reference: str) -> dict:
    """Verify a Paystack transaction by reference"""
    url = f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info("Verifying Paystack transaction: %s", reference)
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            logger.info("Paystack transaction verified: %s", reference)
            return response.json()
    except httpx.HTTPError as e:
        logger.exception("Failed to verify Paystack transaction: %s", reference)
        raise
    
def verify_paystack_signature(payload: bytes, signature: str) -> bool:
    """Verify Paystack webhook signature"""
    computed_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()

    is_valid = hmac.compare_digest(computed_signature, signature)
    if not is_valid:
        logger.warning("Paystack webhook signature verification failed")
    else:
        logger.info("Paystack webhook signature verified successfully")
    return is_valid