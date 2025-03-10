curl -X POST "http://localhost:8004/add-tweet" \
     -H "Content-Type: application/json" \
     -d '{
           "full_text": "fuck you bitches @elon",
           "author_screen_name": "dick",
           "stats": {
             "likes": 10000000000000,
             "retweets": 2,
             "replies": 1,
             "quotte": 0
           }
         }'
