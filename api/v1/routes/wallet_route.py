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
    try:
        if request.amount < 100:  # Minimum 1 naira (100 kobo)
            return fail_response(
                status_code=400,
                message="Minimum deposit is 100 kobo (1 NGN)",
                context={"minimum_amount": 100, "provided": request.amount}
            )
        
        # Get user's wallet
        wallet = Wallet.fetch_one(db, user_id=user.id)
        if not wallet:
            return fail_response(
                status_code=404,
                message="Wallet not found",
                context={"user_id": str(user.id)}
            )
        
        # Generate unique reference
        reference = f"dep_{uuid.uuid4().hex[:16]}"
        
        # Create pending transaction
        transaction = Transaction(
            reference=reference,
            wallet_id=wallet.id,
            user_id=user.id,
            type=TransactionType.DEPOSIT,
            direction=TransactionDirection.CREDIT,
            amount=request.amount,
            status=TransactionStatus.PENDING
        )
        transaction.insert(db)
        
        # Initialize Paystack transaction
        try:
            paystack_response = await initialize_transaction(
                email=user.email,
                amount=request.amount,
                reference=reference
            )
            
            if not paystack_response.get("status"):
                transaction.status = TransactionStatus.FAILED
                transaction.update(db)
                return fail_response(
                    status_code=500,
                    message="Failed to initialize payment",
                    context={"response": paystack_response}
                )
            
            data = paystack_response.get("data", {})
            
            return success_response(
                status_code=200,
                message="Deposit initialized",
                data={
                    "reference": reference,
                    "authorization_url": data.get("authorization_url")
                }
            )
        
        except Exception as e:
            # Mark transaction as failed
            transaction.status = TransactionStatus.FAILED
            transaction.update(db)
            return fail_response(
                status_code=500,
                message="Payment initialization failed",
                context={"error": str(e)}
            )
    
    except Exception as e:
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
    try:
        # Get signature from header
        signature = request.headers.get("x-paystack-signature")
        if not signature:
            return fail_response(
                status_code=400,
                message="Missing signature",
                context={"error": "x-paystack-signature header not found"}
            )
        
        # Get raw body
        body = await request.body()
        
        # Verify signature
        if not verify_paystack_signature(body, signature):
            return fail_response(
                status_code=401,
                message="Invalid signature",
                context={"error": "Signature verification failed"}
            )
        
        # Parse payload
        try:
            payload = await request.json()
        except Exception as e:
            return fail_response(
                status_code=400,
                message="Invalid JSON payload",
                context={"error": str(e)}
            )
        
        # Log webhook
        try:
            webhook_log = Webhook(
                provider="paystack",
                payload=payload,
                headers=dict(request.headers),
                processed=False
            )
            webhook_log.insert(db, commit=False)
        except Exception as e:
            return fail_response(
                status_code=500,
                message="Failed to log webhook",
                context={"error": str(e)}
            )
        
        # Process event
        try:
            event = payload.get("event")
            data = payload.get("data", {})
            
            if event == "charge.success":
                reference = data.get("reference")
                amount = data.get("amount")  # Amount in kobo
                status = data.get("status")
                
                if not reference:
                    webhook_log.processed = True
                    db.commit()
                    return {"status": True}
                
                # Find transaction
                transaction = Transaction.fetch_one(db, reference=reference)
                
                if not transaction:
                    webhook_log.processed = True
                    db.commit()
                    return {"status": True}
                
                # Idempotency check - already processed
                if transaction.status == TransactionStatus.SUCCESS:
                    webhook_log.processed = True
                    db.commit()
                    return {"status": True}
                
                # Update transaction
                if status == "success":
                    transaction.status = TransactionStatus.SUCCESS
                    transaction.extra = data
                    
                    # Credit wallet
                    wallet = Wallet.fetch_one(db, id=transaction.wallet_id)
                    if wallet:
                        wallet.credit(amount)
                        wallet.update(db, commit=False)
                    
                    transaction.update(db, commit=False)
                
                webhook_log.processed = True
                db.commit()
        
        except Exception as e:
            webhook_log.processed = False
            db.commit()
            return fail_response(
                status_code=500,
                message="Failed to process webhook event",
                context={"error": str(e)}
            )
        
        return {"status": True}
    
    except Exception as e:
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
    try:
        transaction = Transaction.fetch_one(db, reference=reference, user_id=user.id)
        
        if not transaction:
            return fail_response(
                status_code=404,
                message="Transaction not found",
                context={"reference": reference}
            )
        
        # Optionally verify with Paystack
        try:
            paystack_data = await verify_transaction(reference)
            paystack_status = paystack_data.get("data", {}).get("status")
            
            return success_response(
                status_code=200,
                message="Transaction status retrieved",
                data={
                    "reference": reference,
                    "status": transaction.status.value,
                    "amount": transaction.amount,
                    "paystack_status": paystack_status
                }
            )
        except Exception:
            return success_response(
                status_code=200,
                message="Transaction status retrieved",
                data={
                    "reference": reference,
                    "status": transaction.status.value,
                    "amount": transaction.amount
                }
            )
    
    except Exception as e:
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
    try:
        wallet = Wallet.fetch_one(db, user_id=user.id)
        
        if not wallet:
            return fail_response(
                status_code=404,
                message="Wallet not found",
                context={"user_id": str(user.id)}
            )
        
        return success_response(
            status_code=200,
            message="Balance retrieved",
            data={
                "balance": wallet.balance,
                "currency": wallet.currency
            }
        )
    
    except Exception as e:
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
    try:
        if request.amount <= 0:
            return fail_response(
                status_code=400,
                message="Invalid amount",
                context={"amount": request.amount, "error": "Amount must be greater than 0"}
            )
        
        # Get sender wallet
        sender_wallet = Wallet.fetch_one(db, user_id=user.id)
        if not sender_wallet:
            return fail_response(
                status_code=404,
                message="Sender wallet not found",
                context={"user_id": str(user.id)}
            )
        
        # Check sufficient balance
        if sender_wallet.balance < request.amount:
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
            return fail_response(
                status_code=404,
                message="Recipient wallet not found",
                context={"wallet_number": request.wallet_number}
            )
        
        if recipient_wallet.id == sender_wallet.id:
            return fail_response(
                status_code=400,
                message="Cannot transfer to self",
                context={"error": "Sender and recipient must be different"}
            )
        
        # Generate unique reference
        reference = f"txf_{uuid.uuid4().hex[:16]}"
        
        # Create debit transaction for sender
        debit_tx = Transaction(
            reference=f"{reference}_debit",
            wallet_id=sender_wallet.id,
            user_id=user.id,
            type=TransactionType.TRANSFER,
            direction=TransactionDirection.DEBIT,
            amount=request.amount,
            status=TransactionStatus.SUCCESS,
            extra={"recipient_wallet": request.wallet_number}
        )
        
        # Create credit transaction for recipient
        credit_tx = Transaction(
            reference=f"{reference}_credit",
            wallet_id=recipient_wallet.id,
            user_id=recipient_wallet.user_id,
            type=TransactionType.TRANSFER,
            direction=TransactionDirection.CREDIT,
            amount=request.amount,
            status=TransactionStatus.SUCCESS,
            extra={"sender_wallet": sender_wallet.wallet_number}
        )
        
        # Link transactions
        debit_tx.insert(db, commit=False)
        credit_tx.related_tx_id = debit_tx.id
        debit_tx.related_tx_id = credit_tx.id
        
        # Update balances
        sender_wallet.debit(request.amount)
        recipient_wallet.credit(request.amount)
        
        # Commit all changes atomically
        credit_tx.insert(db, commit=False)
        sender_wallet.update(db, commit=False)
        recipient_wallet.update(db, commit=False)
        db.commit()
        
        return success_response(
            status_code=200,
            message="Transfer completed",
            data={
                "reference": reference,
                "amount": request.amount,
                "recipient": request.wallet_number
            }
        )
    
    except Exception as e:
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
    try:
        wallet = Wallet.fetch_one(db, user_id=user.id)
        if not wallet:
            return fail_response(
                status_code=404,
                message="Wallet not found",
                context={"user_id": str(user.id)}
            )
        
        transactions = Transaction.fetch_all(db, wallet_id=wallet.id)
        
        transaction_list = [
            {
                "id": str(tx.id),
                "type": tx.type.value,
                "direction": tx.direction.value,
                "amount": tx.amount,
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
            data={"transactions": transaction_list}
        )
    
    except Exception as e:
        return fail_response(
            status_code=500,
            message="Failed to retrieve transaction history",
            context={"error": str(e)}
        )