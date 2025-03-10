curl -X POST "http://localhost:8004/top-k-pagerank" \
     -H "Content-Type: application/json" \
     -d '{
           "graph_label": "arb",
           "k": 10
         }'