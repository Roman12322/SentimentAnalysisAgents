curl -X POST "http://localhost:8004/add-tweets-by-date" \
     -H "Content-Type: application/json" \
     -d '{
           "coin_id": "arb",
           "date_from": "2025-03-05"
         }'
