curl -X POST "http://localhost:8005/get_summary" \
     -H "Content-Type: application/json" \
     -d '{
           "graph_label": "link",
           "k": 10
         }'