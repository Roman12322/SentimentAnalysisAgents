curl -X POST "http://localhost:8005/add-transactions-by-date" \
     -H "Content-Type: application/json" \
     -d '{
           "coin_id": "arb",
           "date_from": "2025-03-05"
         }'
