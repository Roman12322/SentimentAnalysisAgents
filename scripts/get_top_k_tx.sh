curl -X POST "http://localhost:8005/top-k-pagerank" \
     -H "Content-Type: application/json" \
     -d '{
           "graph_label": "arb",
           "k": 10
         }'