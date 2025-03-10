curl -X POST "http://localhost:8005/create-graph" \
     -H "Content-Type: application/json" \
     -d '{
           "coin_id": "link",
           "date_from": "2025-02-11",
           "graph_label": "link"
         }'
