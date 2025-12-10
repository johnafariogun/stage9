# Wallet Service API

A production-ready backend wallet service built with FastAPI, PostgreSQL, and Paystack integration. Provides secure payment processing, transaction management, and dual authentication (JWT + API Keys).

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL 12+
- Paystack account (for payments)
- Google OAuth 2.0 credentials

### Installation

```bash
# Clone repository
git clone https://github.com/idyweb/Wallet_Service_with_Paystack
cd Wallet_Service_with_Paystack

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env .env.local
# Edit .env.local with your credentials
```

### Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/wallet_dev
ENVIRONMENT=development

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# JWT
JWT_SECRET_KEY=your-secret-key-at-least-32-characters
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=10080

# Paystack
PAYSTACK_SECRET_KEY=sk_test_your_paystack_secret_key

# Logging
LOG_LEVEL=INFO
```

### Run Server

```bash
# Apply migrations
alembic upgrade head

# Start development server
uvicorn main:app --reload --port 8000
```

Server runs at: **http://localhost:8000**

API Docs: **http://localhost:8000/docs**

---

## 🔐 Authentication

### Method 1: JWT (User Authentication)

**Step 1: Get OAuth URL**
```bash
curl http://localhost:8000/auth/google
```

**Step 2: Complete OAuth flow in browser, get JWT**
```bash
GET /auth/google/callback?code=<auth_code>
```

**Response:**
```json
{
  "status": "success",
  "message": "Authentication successful",
  "data": {
    "jwt_token": "eyJhbGc...",
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "full_name": "John Doe"
    }
  }
}
```

**Step 3: Use JWT in requests**
```bash
Authorization: Bearer <jwt_token>
```

### Method 2: API Keys (Service-to-Service)

**Create API Key:**
```bash
POST /keys/create
Authorization: Bearer <jwt_token>

{
  "name": "backend-service",
  "permissions": ["deposit", "transfer", "read"],
  "expiry": "1M"
}
```

**Use API Key:**
```bash
x-api-key: sk_live_xxxxx
```

---

## 📡 API Endpoints

### Authentication (`/auth`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/auth/google` | Initiate Google OAuth flow |
| GET | `/auth/google/callback` | OAuth callback (returns JWT) |

### API Keys (`/keys`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/keys/create` | Create new API key |
| POST | `/keys/rollover` | Rollover expired API key |

### Wallet (`/wallet`)
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/wallet/deposit` | Initialize Paystack deposit | JWT/Key (deposit) |
| GET | `/wallet/balance` | Get wallet balance | JWT/Key (read) |
| POST | `/wallet/transfer` | Transfer funds between wallets | JWT/Key (transfer) |
| GET | `/wallet/transactions` | Get transaction history | JWT/Key (read) |
| GET | `/wallet/deposit/{ref}/status` | Check deposit status | JWT/Key (read) |
| POST | `/wallet/paystack/webhook` | Paystack webhook handler | Signature |

---

## 💰 Usage Examples

### 1. Deposit Money

```bash
POST /wallet/deposit
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "amount": 50000
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Deposit initialized",
  "data": {
    "reference": "dep_a1b2c3d4e5f6",
    "authorization_url": "https://checkout.paystack.com/xyz"
  }
}
```

User completes payment at `authorization_url`. Wallet credits automatically via webhook.

### 2. Check Wallet Balance

```bash
GET /wallet/balance
x-api-key: sk_live_xxxxx
```

**Response:**
```json
{
  "status": "success",
  "message": "Balance retrieved",
  "data": {
    "balance": 50000,
    "currency": "NGN"
  }
}
```

### 3. Transfer Funds

```bash
POST /wallet/transfer
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "wallet_number": "a1b2c3d4e5f6",
  "amount": 10000
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Transfer completed",
  "data": {
    "reference": "txf_xyz789",
    "amount": 10000,
    "recipient": "a1b2c3d4e5f6"
  }
}
```

### 4. View Transactions

```bash
GET /wallet/transactions
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "status": "success",
  "message": "Transactions retrieved",
  "data": {
    "transactions": [
      {
        "id": "uuid",
        "type": "deposit",
        "direction": "credit",
        "amount": 50000,
        "status": "success",
        "reference": "dep_a1b2c3d4e5f6",
        "created_at": "2025-12-10T10:30:00Z"
      }
    ]
  }
}
```

### 5. Create API Key

```bash
POST /keys/create
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "name": "mobile-app",
  "permissions": ["deposit", "read"],
  "expiry": "1Y"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "API key created successfully",
  "data": {
    "api_key": "sk_live__xxxxx",
    "expires_at": "2026-12-10T10:30:00Z"
  }
}
```

---

## 🔑 API Key Management

### Permissions
- **`deposit`** - Initialize deposits with Paystack
- **`transfer`** - Transfer funds between wallets
- **`read`** - View balance and transaction history

### Expiry Options
- `1H` - 1 hour
- `1D` - 1 day  
- `1M` - 30 days
- `1Y` - 365 days

### Constraints
- **Max 5 active keys** per user
- Expired keys can be rolled over with new expiry
- Keys shown only once at creation
- SHA256 hashed storage

### Rollover Expired Key

```bash
POST /keys/rollover
Authorization: Bearer <jwt_token>

{
  "expired_key_id": "uuid-of-expired-key",
  "expiry": "1D"
}
```

---

## 💳 Paystack Integration

### Webhook Setup

1. Login to Paystack Dashboard
2. Go to Settings → API Keys & Webhooks
3. Add webhook URL: `https://yourdomain.com/wallet/paystack/webhook`
4. Select events: `charge.success`

### Testing Payments

**Test Credentials:**
```
Card Number: 4084 0840 8408 4081
Expiry: Any future date
CVV: Any 3 digits
OTP: 123456
```

For full testing guide: https://paystack.com/docs/payments/test-payments/

### Webhook Security
- Paystack signs webhooks with HMAC-SHA512
- Signature verified on each webhook request
- Idempotent processing prevents duplicate credits

---

## 🛡️ Security Features

| Feature | Implementation |
|---------|-----------------|
| **Authentication** | JWT (Google OAuth 2.0) + API Key auth |
| **API Key Storage** | SHA256 hashing |
| **Webhook Verification** | HMAC-SHA512 signature validation |
| **Token Expiration** | JWT: 7 days, API Keys: configurable (1H-1Y) |
| **Access Control** | Permission-based (deposit/transfer/read) |
| **Transactions** | Atomic database operations |
| **Balance Checks** | Prevent insufficient fund transfers |
| **Error Handling** | Comprehensive try-except with logging |
| **Correlation IDs** | Request tracing via logging |

---

## ⚠️ Error Responses

All errors follow standardized format:

```json
{
  "status": "failure",
  "status_code": 400,
  "message": "Invalid request",
  "error": {
    "field": "error details"
  }
}
```

### Common Errors

| Code | Message | Cause |
|------|---------|-------|
| 400 | Minimum deposit is 100 kobo | Amount too small |
| 400 | Maximum 5 active API keys | Key limit reached |
| 400 | Invalid expiry format | Use: 1H, 1D, 1M, 1Y |
| 401 | API key is revoked or expired | Key invalid or expired |
| 401 | Authentication required | Missing/invalid auth |
| 403 | Insufficient API key permissions | Missing permission |
| 404 | Wallet not found | User wallet missing |
| 404 | Transaction not found | Invalid reference |
| 500 | Failed to initialize payment | Paystack error |

---

## 📊 Database Schema

### Users
```
- id (UUID, Primary Key)
- google_id (String, Unique) - Google OAuth ID
- email (String, Unique)
- full_name (String)
- created_at (DateTime)
```

### Wallets
```
- id (UUID, Primary Key)
- user_id (UUID, Foreign Key → users)
- wallet_number (String, Unique) - Identifier for transfers
- balance (BigInteger) - Amount in kobo
- currency (String) - Default: NGN
- created_at (DateTime)
```

### Transactions
```
- id (UUID, Primary Key)
- reference (String, Unique)
- wallet_id (UUID, Foreign Key → wallets)
- user_id (UUID, Foreign Key → users)
- type (Enum) - deposit, transfer, withdrawal
- direction (Enum) - credit, debit
- amount (BigInteger) - Amount in kobo
- status (Enum) - pending, success, failed
- related_tx_id (UUID) - Link transfer pairs
- extra (JSON) - Additional metadata
- created_at (DateTime)
```

### API Keys
```
- id (UUID, Primary Key)
- user_id (UUID, Foreign Key → users)
- name (String)
- hashed_key (String) - SHA256 hashed
- permissions (Array[String]) - deposit, transfer, read
- expires_at (DateTime)
- revoked (Boolean)
- created_at (DateTime)
```

### Webhooks
```
- id (UUID, Primary Key)
- provider (String) - e.g., "paystack"
- payload (JSON) - Raw webhook data
- headers (JSON) - Request headers
- processed (Boolean)
- created_at (DateTime)
```

---

## 🚀 Deployment

### Production Checklist
- [ ] Use strong `JWT_SECRET_KEY` (min 32 chars)
- [ ] Configure production Paystack keys
- [ ] Set up HTTPS/SSL certificates
- [ ] Configure PostgreSQL backups
- [ ] Set `ENVIRONMENT=production`
- [ ] Update webhook URL in Paystack dashboard
- [ ] Set `LOG_LEVEL=INFO` or `WARNING`
- [ ] Configure CORS origins
- [ ] Enable database connection pooling
- [ ] Set up application monitoring

### Docker Deployment

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 📝 Development

### Project Structure
```
├── api/
│   ├── db/
│   │   ├── base_model.py
│   │   ├── database.py
│   │   └── __init__.py
│   ├── utils/
│   │   ├── api_key.py
│   │   ├── deps.py
│   │   ├── logger.py
│   │   ├── paystack.py
│   │   ├── responses.py
│   │   ├── security.py
│   │   └── __init__.py
│   └── v1/
│       ├── models/
│       │   ├── api_key.py
│       │   ├── transaction.py
│       │   ├── user.py
│       │   ├── wallet.py
│       │   └── webhook.py
│       └── routes/
│           ├── auth_route.py
│           ├── api_key_route.py
│           ├── wallet_route.py
│           └── __init__.py
├── alembic/
├── main.py
├── requirements.txt
└── .env
```

### Running Tests
```bash
pytest -v
```

### Database Migrations
```bash
# Create migration
alembic revision --autogenerate -m "Add field"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Logging
- Structured JSON logging with correlation IDs
- Logs to stdout (Docker-friendly)
- Configurable level: DEBUG, INFO, WARNING, ERROR

---

## 📚 API Documentation

Automatic interactive API documentation:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI Schema:** `http://localhost:8000/openapi.json`

---

## 🤝 Contributing

1. Fork repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

---

## 📞 Support

- **Issues:** Create an issue on GitHub
- **Paystack Docs:** https://paystack.com/docs
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **PostgreSQL Docs:** https://www.postgresql.org/docs
