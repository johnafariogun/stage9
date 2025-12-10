curl -X POST \
  'http://localhost:8000/keys/create' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhMTFkNDNjYS0zYjY3LTRhOGYtYWNiZi01YmNlZjBmYmU2YTciLCJlbWFpbCI6ImFmYXJpb2d1bi5qb2huMjAwMkBnbWFpbC5jb20iLCJpYXQiOjE3NjUzNzc4OTcsImV4cCI6MTc2NTk3NzgzN30.gx8mTxhpYprj3_cgIs1ctzIDchHoJZtyDX5oMKvSfB4' \
  -H 'Content-Type: application/json' \
  -d '{ 
  "name": "Strong key", 
  "permissions": ["deposit", "transfer", "read"], 
  "expiry": "1H"
}'


# curl -X 'POST' \
#   'http://localhost:8000/wallet/deposit' \
#   -H 'accept: application/json' \
#   -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhMTFkNDNjYS0zYjY3LTRhOGYtYWNiZi01YmNlZjBmYmU2YTciLCJlbWFpbCI6ImFmYXJpb2d1bi5qb2huMjAwMkBnbWFpbC5jb20iLCJpYXQiOjE3NjUzNzU3MzUsImV4cCI6MTc2NTk3NTY3NX0.NzxlMWFxxaoL7uF-fg_Xru-SISYUfXUNT9PGjUatI-c' \
#   -H 'Content-Type: application/json' \
#   -d '{
#   "amount": 10000
# }'

# curl -X 'POST' \
#   'https://stage9-sc0o.onrender.com/wallet/deposit' \
#   -H 'accept: application/json' \
#   -H 'X-API-KEY: sk_live__HLuTcbdL3dd371icdPdoiWvlHBsq3BGAjpg_xcKonhc' \
#   -H 'Content-Type: application/json' \
#   -d '{
#   "amount": 10000
# }'

# curl -X 'GET' \
#   'https://stage9-sc0o.onrender.com/wallet/deposit/dep_5766112c930d41e9/status' \
#   -H 'X-API-KEY: sk_live__HLuTcbdL3dd371icdPdoiWvlHBsq3BGAjpg_xcKonhc' \
#   -H 'accept: application/json'



# curl https://api.paystack.co/transaction/initialize \
# -H "Authorization: Bearer sk_test_6efd28e745bfd063bff1b312d9ff4807bdc9bf54" \
# -H "Content-Type: application/json" \
# -d '{
#     "amount": 500000,
#     "email": "customer@email.com",
#     "currency": "NGN"
# }' \
# -X POST

# curl -X 'GET' \
#   'https://stage9-sc0o.onrender.com/wallet/balance' \
#   -H 'X-API-KEY: sk_live__HLuTcbdL3dd371icdPdoiWvlHBsq3BGAjpg_xcKonhc' \
#   -H 'accept: application/json'

curl -X 'GET' \
  'localhost:8000/wallet/transactions' \
  -H 'accept: application/json' \
  -H 'X-API-KEY: sk_live__l3-9vGFJC6TCap43p0X6yFQNvvlB_RatiCYLfEYHoV0'