import os
import httpx
import hmac
import hashlib
from dotenv import load_dotenv
from .logger import logger

load_dotenv()

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"


async def initialize_transaction(email: str, amount: int, reference: str) -> dict:
    """Initiate a Paystack transaction
    Amount should be in kobo for NGN currency"""
    transaction_url = f"{PAYSTACK_BASE_URL}/transaction/initialize"
    request_headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    request_payload = {
        "email": email,
        "amount": amount,
        "reference": reference
    }

    try:
        async with httpx.AsyncClient() as http_client:
            logger.info("Initializing Paystack transaction for email: %s, amount: %s, reference: %s", email, amount, reference)
            response = await http_client.post(transaction_url, json=request_payload, headers=request_headers)
            response.raise_for_status()
            logger.info("Paystack transaction initialized successfully: %s", reference)
            return response.json()
    except httpx.HTTPError as e:
        logger.exception("Failed to initialize Paystack transaction for reference: %s", reference)
        raise
    

async def verify_transaction(reference: str) -> dict:
    """Verify a Paystack transaction by reference"""
    verification_url = f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}"
    request_headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }

    try:
        async with httpx.AsyncClient() as http_client:
            logger.info("Verifying Paystack transaction: %s", reference)
            response = await http_client.get(verification_url, headers=request_headers)
            response.raise_for_status()
            logger.info("Paystack transaction verified: %s", reference)
            return response.json()
    except httpx.HTTPError as e:
        logger.exception("Failed to verify Paystack transaction: %s", reference)
        raise
    
def verify_paystack_signature(webhook_payload: bytes, signature_header: str) -> bool:
    """Verify Paystack webhook signature"""
    computed_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode('utf-8'),
        webhook_payload,
        hashlib.sha512
    ).hexdigest()

    is_valid = hmac.compare_digest(computed_signature, signature_header)
    if not is_valid:
        logger.warning("Paystack webhook signature verification failed")
    else:
        logger.info("Paystack webhook signature verified successfully")
    return is_valid