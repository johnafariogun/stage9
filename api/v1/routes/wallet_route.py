import uuid
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from api.utils.logger import logger

from api.db.database import get_db
from api.v1.models.wallet import Wallet
from api.v1.models.transaction import Transaction, TransactionType, TransactionDirection, TransactionStatus
from api.v1.models.webhook import Webhook
from api.utils.deps import require_permission
from api.utils.paystack import initialize_transaction, verify_transaction, verify_paystack_signature
from api.utils.responses import success_response, fail_response

router = APIRouter(prefix="/wallet", tags=["Wallet"])


def kobo_to_naira(amount_in_kobo: int) -> float:
    """Convert amount from kobo (smallest currency unit) to naira.
    
    1 Naira = 100 Kobo
    Example: 1055 kobo = 10.55 NGN
    """
    return round(amount_in_kobo / 100, 2)


class DepositRequest(BaseModel):
    amount: int  # Amount in kobo


class TransferRequest(BaseModel):
    wallet_number: str
    amount: int  # Amount in kobo


@router.post("/deposit")
async def deposit_to_wallet(
    request: DepositRequest,
    user = Depends(require_permission("deposit")),
    db: Session = Depends(get_db)
):
    """Initialize Paystack deposit transaction"""
    logger.info(f"Deposit request received for user_id: {user.id}, amount: {request.amount}")
    try:
        if request.amount < 100:  # Minimum 1 naira (100 kobo)
            logger.warning(f"Deposit failed: Amount too low. User_id: {user.id}, amount: {request.amount}")
            return fail_response(
                status_code=400,
                message="Minimum deposit is 100 kobo (1 NGN)",
                context={"minimum_amount": 100, "provided": request.amount}
            )
        
        # Get user's wallet
        user_wallet = Wallet.fetch_one(db, user_id=user.id)
        if not user_wallet:
            logger.error(f"Deposit failed: Wallet not found for user_id: {user.id}")
            return fail_response(
                status_code=404,
                message="Wallet not found",
                context={"user_id": str(user.id)}
            )
        
        # Generate unique reference
        transaction_reference = f"dep_{uuid.uuid4().hex[:16]}"
        logger.debug(f"Generated reference {transaction_reference} for deposit by user {user.id}")
        
        # Create pending transaction
        deposit_transaction = Transaction(
            reference=transaction_reference,
            wallet_id=user_wallet.id,
            user_id=user.id,
            type=TransactionType.DEPOSIT,
            direction=TransactionDirection.CREDIT,
            amount=request.amount,
            status=TransactionStatus.PENDING
        )
        deposit_transaction.insert(db)
        logger.info(f"Pending transaction created: {transaction_reference} for user {user.id}")
        
        # Initialize Paystack transaction
        try:
            paystack_response = await initialize_transaction(
                email=user.email,
                amount=request.amount,
                reference=transaction_reference
            )
            
            if not paystack_response.get("status"):
                logger.error(f"Paystack initialization failed for reference {transaction_reference}: {paystack_response.get('message')}")
                deposit_transaction.status = TransactionStatus.FAILED
                deposit_transaction.update(db)
                return fail_response(
                    status_code=500,
                    message="Failed to initialize payment",
                    context={"response": paystack_response}
                )
            
            response_data = paystack_response.get("data", {})
            logger.info(f"Paystack initialization successful for reference {transaction_reference}. Auth URL: {response_data.get('authorization_url')}")
            
            return success_response(
                status_code=200,
                message="Deposit initialized",
                data={
                    "reference": transaction_reference,
                    "authorization_url": response_data.get("authorization_url"),
                    "wallet_number": user_wallet.wallet_number
                }
            )
        
        except Exception as e:
            logger.exception(f"Exception during Paystack initialization for reference {transaction_reference}")
            # Mark transaction as failed
            deposit_transaction.status = TransactionStatus.FAILED
            deposit_transaction.update(db)
            return fail_response(
                status_code=500,
                message="Payment initialization failed",
                context={"error": str(e)}
            )
    
    except Exception as e:
        logger.exception(f"Unhandled exception in deposit_to_wallet for user {user.id}")
        return fail_response(
            status_code=500,
            message="Failed to process deposit request",
            context={"error": str(e)}
        )


@router.post("/paystack/webhook")
async def paystack_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Paystack webhook events"""
    logger.info("Paystack webhook received.")
    try:
        # Get signature from header
        signature_header = request.headers.get("x-paystack-signature")
        if not signature_header:
            logger.error("Webhook failed: Missing x-paystack-signature header.")
            return fail_response(
                status_code=400,
                message="Missing signature",
                context={"error": "x-paystack-signature header not found"}
            )
        
        # Get raw body
        webhook_body = await request.body()
        
        # Verify signature
        if not verify_paystack_signature(webhook_body, signature_header):
            logger.error("Webhook failed: Invalid signature.")
            return fail_response(
                status_code=401,
                message="Invalid signature",
                context={"error": "Signature verification failed"}
            )
        
        # Parse payload
        try:
            webhook_payload = await request.json()
            logger.debug(f"Webhook payload: {webhook_payload}")
        except Exception as e:
            logger.error(f"Webhook failed: Invalid JSON payload. Error: {e}")
            return fail_response(
                status_code=400,
                message="Invalid JSON payload",
                context={"error": str(e)}
            )
        
        # Log webhook
        webhook_log = None
        try:
            webhook_log = Webhook(
                provider="paystack",
                payload=webhook_payload,
                headers=dict(request.headers),
                processed=False
            )
            webhook_log.insert(db, commit=False)
            logger.info(f"Webhook event logged: {webhook_payload.get('event')}")
        except Exception as e:
            logger.exception(f"Failed to log webhook event: {webhook_payload.get('event')}. Error: {e}")
            # Attempt to commit even if logging failed, processing may still be necessary
            # For simplicity in this example, we return fail, but in production, may need a retry mechanism.
            return fail_response(
                status_code=500,
                message="Failed to log webhook",
                context={"error": str(e)}
            )
        
        # Process event
        try:
            event_type = webhook_payload.get("event")
            event_data = webhook_payload.get("data", {})
            
            if event_type == "charge.success":
                transaction_reference = event_data.get("reference")
                transaction_amount = event_data.get("amount")  # Amount in kobo
                transaction_status = event_data.get("status")
                logger.info(f"Processing charge.success for reference: {transaction_reference}, status: {transaction_status}")
                
                if not transaction_reference:
                    logger.warning("charge.success event missing reference. Ignoring.")
                    webhook_log.processed = True
                    db.commit()
                    return {"status": True}
                
                # Find transaction
                found_transaction = Transaction.fetch_one(db, reference=transaction_reference)
                
                if not found_transaction:
                    logger.warning(f"charge.success: Transaction not found for reference: {transaction_reference}. Ignoring.")
                    webhook_log.processed = True
                    db.commit()
                    return {"status": True}
                
                # Idempotency check - already processed
                if found_transaction.status == TransactionStatus.SUCCESS:
                    logger.info(f"Transaction {transaction_reference} already processed (SUCCESS). Idempotency check passed.")
                    webhook_log.processed = True
                    db.commit()
                    return {"status": True}
                
                # Update transaction
                if transaction_status == "success":
                    logger.info(f"Updating transaction {transaction_reference} to SUCCESS and crediting wallet.")
                    found_transaction.status = TransactionStatus.SUCCESS
                    found_transaction.extra = event_data
                    
                    # Credit wallet
                    transaction_wallet = Wallet.fetch_one(db, id=found_transaction.wallet_id)
                    if transaction_wallet:
                        transaction_wallet.credit(transaction_amount)
                        transaction_wallet.update(db, commit=False)
                        logger.info(f"Wallet {transaction_wallet.id} credited with {transaction_amount} kobo.")
                    else:
                        logger.error(f"Wallet not found for transaction {transaction_reference}. Could not credit.")
                    
                    found_transaction.update(db, commit=False)
                elif transaction_status == "failed":
                    logger.warning(f"Transaction {transaction_reference} failed according to Paystack webhook.")
                    found_transaction.status = TransactionStatus.FAILED
                    found_transaction.update(db, commit=False)
                else:
                    logger.info(f"Webhook status for {transaction_reference} is '{transaction_status}', not 'success'. Transaction status remains: {found_transaction.status.value}")
                    
                webhook_log.processed = True
                db.commit()
                logger.info(f"Webhook processing completed and committed for reference {transaction_reference}.")
            else:
                logger.info(f"Webhook event type '{event_type}' received. Not charge.success, ignoring for now.")
                webhook_log.processed = True
                db.commit()
        
        except Exception as e:
            logger.exception(f"Exception during webhook event processing for event: {webhook_payload.get('event')}")
            if webhook_log:
                webhook_log.processed = False
            db.commit() # Commit the webhook log even if processing failed
            return fail_response(
                status_code=500,
                message="Failed to process webhook event",
                context={"error": str(e)}
            )
        
        return {"status": True}
    
    except Exception as e:
        logger.exception("Unhandled exception in paystack_webhook endpoint")
        return fail_response(
            status_code=500,
            message="Webhook processing failed",
            context={"error": str(e)}
        )


@router.get("/deposit/{reference}/status")
async def check_deposit_status(
    reference: str,
    user = Depends(require_permission("read")),
    db: Session = Depends(get_db)
):
    """Check deposit transaction status (does not credit wallet)"""
    logger.info(f"Status check requested for reference: {reference} by user {user.id}")
    try:
        status_transaction = Transaction.fetch_one(db, reference=reference, user_id=user.id)
        
        if not status_transaction:
            logger.warning(f"Status check failed: Transaction not found for reference: {reference}, user: {user.id}")
            return fail_response(
                status_code=404,
                message="Transaction not found",
                context={"reference": reference}
            )
        
        # Fetch wallet for this transaction (to return wallet_number)
        transaction_wallet = Wallet.fetch_one(db, id=status_transaction.wallet_id)

        # Optionally verify with Paystack
        try:
            paystack_data = await verify_transaction(reference)
            paystack_status = paystack_data.get("data", {}).get("status")
            logger.info(f"Paystack verification for {reference}: Paystack status is {paystack_status}, internal status is {status_transaction.status.value}")
            
            return success_response(
                status_code=200,
                message="Transaction status retrieved",
                data={
                    "reference": reference,
                    "status": status_transaction.status.value,
                    "amount": kobo_to_naira(status_transaction.amount),
                    "currency": "NGN",
                    "paystack_status": paystack_status,
                    "wallet_number": transaction_wallet.wallet_number if transaction_wallet else None
                }
            )
        except Exception as e:
            logger.warning(f"Paystack verification failed for reference {reference}. Returning internal status. Error: {e}")
            return success_response(
                status_code=200,
                message="Transaction status retrieved (Paystack verification failed)",
                data={
                    "reference": reference,
                    "status": status_transaction.status.value,
                    "amount": kobo_to_naira(status_transaction.amount),
                    "currency": "NGN",
                    "wallet_number": transaction_wallet.wallet_number if transaction_wallet else None
                }
            )
    
    except Exception as e:
        logger.exception(f"Unhandled exception in check_deposit_status for reference {reference}")
        return fail_response(
            status_code=500,
            message="Failed to check transaction status",
            context={"error": str(e)}
        )


@router.get("/balance")
async def get_wallet_balance(
    user = Depends(require_permission("read")),
    db: Session = Depends(get_db)
):
    """Get wallet balance"""
    logger.info(f"Balance request for user {user.id}")
    try:
        balance_wallet = Wallet.fetch_one(db, user_id=user.id)
        
        if not balance_wallet:
            logger.error(f"Balance request failed: Wallet not found for user_id: {user.id}")
            return fail_response(
                status_code=404,
                message="Wallet not found",
                context={"user_id": str(user.id)}
            )
        
        logger.info(f"Balance retrieved for wallet {balance_wallet.wallet_number}: {balance_wallet.balance}")
        return success_response(
            status_code=200,
            message="Balance retrieved",
            data={
                "balance": kobo_to_naira(balance_wallet.balance),
                "currency": balance_wallet.currency,
                "wallet_number": balance_wallet.wallet_number
            }
        )
    
    except Exception as e:
        logger.exception(f"Unhandled exception in get_wallet_balance for user {user.id}")
        return fail_response(
            status_code=500,
            message="Failed to retrieve wallet balance",
            context={"error": str(e)}
        )


@router.post("/transfer")
async def transfer_funds(
    request: TransferRequest,
    user = Depends(require_permission("transfer")),
    db: Session = Depends(get_db)
):
    """Transfer funds to another wallet"""
    logger.info(f"Transfer request from user {user.id} to {request.wallet_number} for amount {request.amount}")
    try:
        if request.amount <= 0:
            logger.warning(f"Transfer failed: Invalid amount {request.amount} from user {user.id}")
            return fail_response(
                status_code=400,
                message="Invalid amount",
                context={"amount": request.amount, "error": "Amount must be greater than 0"}
            )
        
        # Get sender wallet
        sender_wallet = Wallet.fetch_one(db, user_id=user.id)
        if not sender_wallet:
            logger.error(f"Transfer failed: Sender wallet not found for user_id: {user.id}")
            return fail_response(
                status_code=404,
                message="Sender wallet not found",
                context={"user_id": str(user.id)}
            )
        
        # Check sufficient balance
        if sender_wallet.balance < request.amount:
            logger.warning(f"Transfer failed: Insufficient balance {sender_wallet.balance} for user {user.id}. Required: {request.amount}")
            return fail_response(
                status_code=400,
                message="Insufficient balance",
                context={
                    "balance": sender_wallet.balance,
                    "required": request.amount
                }
            )
        
        # Get recipient wallet
        recipient_wallet = Wallet.fetch_one(db, wallet_number=request.wallet_number)
        if not recipient_wallet:
            logger.warning(f"Transfer failed: Recipient wallet not found for wallet_number: {request.wallet_number}")
            return fail_response(
                status_code=404,
                message="Recipient wallet not found",
                context={"wallet_number": request.wallet_number}
            )
        
        if recipient_wallet.id == sender_wallet.id:
            logger.warning(f"Transfer failed: Attempt to transfer to self by user {user.id}")
            return fail_response(
                status_code=400,
                message="Cannot transfer to self",
                context={"error": "Sender and recipient must be different"}
            )
        
        # Generate unique reference
        transfer_reference = f"txf_{uuid.uuid4().hex[:16]}"
        logger.debug(f"Generated reference {transfer_reference} for transfer from {sender_wallet.wallet_number} to {recipient_wallet.wallet_number}")
        
        # Create debit transaction for sender
        debit_transaction = Transaction(
            reference=f"{transfer_reference}_debit",
            wallet_id=sender_wallet.id,
            user_id=user.id,
            type=TransactionType.TRANSFER,
            direction=TransactionDirection.DEBIT,
            amount=request.amount,
            status=TransactionStatus.SUCCESS,
            extra={"recipient_wallet": request.wallet_number}
        )
        
        # Create credit transaction for recipient
        credit_transaction = Transaction(
            reference=f"{transfer_reference}_credit",
            wallet_id=recipient_wallet.id,
            user_id=recipient_wallet.user_id,
            type=TransactionType.TRANSFER,
            direction=TransactionDirection.CREDIT,
            amount=request.amount,
            status=TransactionStatus.SUCCESS,
            extra={"sender_wallet": sender_wallet.wallet_number}
        )
        
        # Link transactions (IDs will be available after first insert/session flush)
        debit_transaction.insert(db, commit=False)
        db.flush() # Ensure debit_tx has an ID
        credit_transaction.related_tx_id = debit_transaction.id
        debit_transaction.related_tx_id = credit_transaction.id
        
        # Update balances
        sender_wallet.debit(request.amount)
        recipient_wallet.credit(request.amount)
        
        logger.info(f"Transfer successful: Debiting {request.amount} from {sender_wallet.wallet_number} and crediting {recipient_wallet.wallet_number}")
        
        # Commit all changes atomically
        credit_transaction.insert(db, commit=False) # Inserting credit tx after updating its related_tx_id
        sender_wallet.update(db, commit=False)
        recipient_wallet.update(db, commit=False)
        db.commit()
        
        return success_response(
            status_code=200,
            message="Transfer completed",
            data={
                "reference": transfer_reference,
                "amount": kobo_to_naira(request.amount),
                "currency": "NGN",
                "recipient": request.wallet_number,
                "sender_wallet": sender_wallet.wallet_number,
                "recipient_wallet": recipient_wallet.wallet_number
            }
        )
    
    except Exception as e:
        logger.exception(f"Exception during fund transfer by user {user.id}")
        db.rollback() # Rollback changes in case of failure
        return fail_response(
            status_code=500,
            message="Transfer failed",
            context={"error": str(e)}
        )


@router.get("/transactions")
async def get_transaction_history(
    user = Depends(require_permission("read")),
    db: Session = Depends(get_db)
):
    """Get transaction history"""
    logger.info(f"Transaction history request for user {user.id}")
    try:
        wallet = Wallet.fetch_one(db, user_id=user.id)
        if not wallet:
            logger.error(f"Transaction history failed: Wallet not found for user_id: {user.id}")
            return fail_response(
                status_code=404,
                message="Wallet not found",
                context={"user_id": str(user.id)}
            )
        
        transactions = Transaction.fetch_all(db, wallet_id=wallet.id)
        logger.info(f"Retrieved {len(transactions)} transactions for user {user.id}")
        
        transaction_list = [
            {
                "id": str(tx.id),
                "type": tx.type.value,
                "direction": tx.direction.value,
                "amount": kobo_to_naira(tx.amount),
                "currency": "NGN",
                "status": tx.status.value,
                "reference": tx.reference,
                "created_at": tx.created_at.isoformat(),
                "extra": tx.extra
            }
            for tx in transactions
        ]
        
        return success_response(
            status_code=200,
            message="Transactions retrieved",
            data={
                "wallet_number": wallet.wallet_number,
                "transactions": transaction_list
            }
        )
    
    except Exception as e:
        logger.exception(f"Unhandled exception in get_transaction_history for user {user.id}")
        return fail_response(
            status_code=500,
            message="Failed to retrieve transaction history",
            context={"error": str(e)}
        )