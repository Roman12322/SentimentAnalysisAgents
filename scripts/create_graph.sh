curl -X POST "http://localhost:8004/create-graph" \
     -H "Content-Type: application/json" \
     -d '{
           "coin_id": "link",
           "date_from": "2023-01-01",
           "graph_label": "link"
         }'
