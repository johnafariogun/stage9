# curl -X POST \
#   'http://localhost:8000/keys/create' \
#   -H 'accept: application/json' \
#   -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhMTFkNDNjYS0zYjY3LTRhOGYtYWNiZi01YmNlZjBmYmU2YTciLCJlbWFpbCI6ImFmYXJpb2d1bi5qb2huMjAwMkBnbWFpbC5jb20iLCJpYXQiOjE3NjUzNzI1NzYsImV4cCI6MTc2NTk3MjUxNn0.u7AQm0d09xcho0lR7T6iTC9Cc9tqKLXHZ6efbTJVGck' \
#   -H 'Content-Type: application/json' \
#   -d '{ 
#   "name": "Strong key", 
#   "permissions": ["deposit", "transfer", "read"], 
#   "expiry": "1H"
# }'


# curl -X 'POST' \
#   'http://localhost:8000/wallet/deposit' \
#   -H 'accept: application/json' \
#   -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhMTFkNDNjYS0zYjY3LTRhOGYtYWNiZi01YmNlZjBmYmU2YTciLCJlbWFpbCI6ImFmYXJpb2d1bi5qb2huMjAwMkBnbWFpbC5jb20iLCJpYXQiOjE3NjUzNzI1NzYsImV4cCI6MTc2NTk3MjUxNn0.u7AQm0d09xcho0lR7T6iTC9Cc9tqKLXHZ6efbTJVGck' \
#   -H 'Content-Type: application/json' \
#   -d '{
#   "amount": 10000
# }'

curl -X 'POST' \
  'http://localhost:8000/wallet/deposit' \
  -H 'accept: application/json' \
  -H 'X-API-KEY: sk_live__MNoNcP2BqhAD9V6LylWKjE0VQNiLH0O_GAiIE9a_Yf8' \
  -H 'Content-Type: application/json' \
  -d '{
  "amount": 10000
}'