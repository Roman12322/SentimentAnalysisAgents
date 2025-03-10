from fastapi import FastAPI, HTTPException
import uvicorn
import networkx as nx
from pydantic import BaseModel
from typing import List
from requests_and_responses import GraphRequest, TopKRequest
from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE, CONNECTION_STRING
import re
import ast
from tqdm import tqdm
from neo4j import GraphDatabase
import json
import pandas as pd
import psycopg2  # For PostgreSQL
from transformers import pipeline
import redis

# ----------------------------
# Initialize Redis client for deduplication
# ----------------------------
redis_client = redis.Redis(host='localhost', port=26379, db=0)

# ----------------------------
# Initialize FastAPI and sentiment analysis model
# ----------------------------
app = FastAPI()
sentiment_model = pipeline("sentiment-analysis", model='nlptown/bert-base-multilingual-uncased-sentiment')

# ----------------------------
# Helper functions for sentiment and score interpolation
# ----------------------------
def get_range(label):
    ranges = {   
        '5 stars': [0.66, 1], 
        '4 stars': [0.33, 0.65],
        '3 stars': [-0.32, 0.32],
        '2 stars': [-0.65, -0.32],
        '1 star': [-0.66, -1]
    }
    return ranges.get(label)

def interpolate_score_within_range(pred_score, range_min, range_max):
    if pred_score == 0:
        return (range_min + range_max) / 2
    interpolated_score = range_min + pred_score * (range_max - range_min)
    return interpolated_score

def compute_semantic_metric(model_output: dict):
    ranges = {   
        '5 stars': [0.66, 1], 
        '4 stars': [0.33, 0.65],
        '3 stars': [-0.32, 0.32],
        '2 stars': [-0.65, -0.32],
        '1 stars': [-0.66, -1]
    }
    semantic_scores = []
    label = model_output['label']
    pred_score = model_output['score']
    range_for_label = get_range(label)
    if range_for_label:
        range_min, range_max = range_for_label
        semantic_score = interpolate_score_within_range(pred_score, range_min, range_max)
        semantic_scores.append({
            'label': label,
            'predicted_score': pred_score,
            'semantic_score': semantic_score
        })
    return semantic_scores

def analyze_sentiment(text):
    results = sentiment_model([text])
    # Using the predicted score for simplicity; you could also use semantic_score if desired.
    return compute_semantic_metric(results[0])[0]['predicted_score']

# ----------------------------
# Helper functions for tweet deduplication using Redis
# ----------------------------
def store_processed_tweet(tweet_id: str, coin_id: str = ""):
    # Use a Redis set, optionally keyed by coin_id for partitioning
    key = f"processed_tweets:{coin_id}" if coin_id else "processed_tweets"
    redis_client.sadd(key, tweet_id)

def is_tweet_processed(tweet_id: str, coin_id: str = "") -> bool:
    key = f"processed_tweets:{coin_id}" if coin_id else "processed_tweets"
    return redis_client.sismember(key, tweet_id)

# ----------------------------
# Functions for extracting data from tweets
# ----------------------------
def extract_mentions(text):
    return re.findall(r'@(\w+[\w\._]*)', text.lower())

def extract_likes(row):
    return row.get('likes', 0) if row else 0

def extract_reply(row):
    return row.get('reply', 0) if row else 0

def extract_retweet(row):
    return row.get('retweet', 0) if row else 0

def extract_quotte(row):
    return row.get('quotte', 0) if row else 0

# ----------------------------
# Function to get coin data from PostgreSQL
# ----------------------------
def get_coin_data(coin_id: str, data_from: str):
    query = f"""
    SELECT tp.id as message_id, tp.full_text, tp.stats, tp.published_at, tp.created_at, tp.updated_at, tp.author_screen_name, tcc.coin_id 
    FROM tw_post tp
    INNER JOIN tw_channel_coin tcc ON tp.channel_id = tcc.channel_id 
    WHERE tcc.coin_id = '{coin_id}' AND tp.created_at > '{data_from}'
    """
    conn_str = f"{CONNECTION_STRING}"
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    cur.execute(query)
    dataset = cur.fetchall()
    conn.close()
    data = [{
        'message_id': item[0],
        'full_text': item[1],
        'stats': item[2],
        'published_at': item[3],
        'created_at': item[4],
        'updated_at': item[5],
        'author_screen_name': item[6],
        'coin_id': item[7]
    } for item in dataset]
    d = pd.DataFrame(data)
    return d

# ----------------------------
# Function to create a graph from tweets
# ----------------------------
def create_graph(coin_id: str, data_from: str):
    twitter_df = get_coin_data(coin_id, data_from)
    tqdm.pandas()  # Enable progress_apply for pandas

    twitter_df['likes'] = twitter_df['stats'].progress_apply(extract_likes)
    twitter_df['replies'] = twitter_df['stats'].progress_apply(extract_reply)
    twitter_df['retweets'] = twitter_df['stats'].progress_apply(extract_retweet)
    twitter_df['quottes'] = twitter_df['stats'].progress_apply(extract_quotte)
    twitter_df['mentions'] = twitter_df['full_text'].progress_apply(extract_mentions)
    twitter_df['sentiment'] = twitter_df['full_text'].progress_apply(analyze_sentiment)

    G = nx.DiGraph()
    for _, row in twitter_df.iterrows():
        author = row['author_screen_name']
        mentions = row['mentions']
        likes = row['likes']
        retweets = row['retweets']
        replies = row['replies']
        quottes = row['quottes']
        sentiment = row['sentiment']

        for mention in mentions:
            weight = likes + retweets + replies + quottes
            if weight == 0:
                weight = 1
            G.add_edge(author, mention, weight=weight, sentiment=sentiment)
    return G, twitter_df

# ----------------------------
# Function to add a NetworkX graph to Neo4j
# ----------------------------
def add_networkx_graph_to_neo4j(G: nx.DiGraph, graph_label: str):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DATABASE) as session:
        for node in G.nodes:
            session.run(
                """
                MERGE (u:User {screen_name: $screen_name})
                ON CREATE SET u.graph_labels = [$graph_label]
                ON MATCH SET u.graph_labels = 
                    CASE 
                        WHEN NOT $graph_label IN u.graph_labels THEN u.graph_labels + $graph_label
                        ELSE u.graph_labels
                    END
                """, screen_name=node, graph_label=graph_label+"_posts")

        for source, target, data in G.edges(data=True):
            weight = data.get('weight', 1)
            sentiment = data.get('sentiment', None)
            session.run(
                """
                MATCH (a:User {screen_name: $source}), (b:User {screen_name: $target})
                MERGE (a)-[r:MENTIONS]->(b)
                ON CREATE SET r.graph_labels = [$graph_label]
                ON MATCH SET r.graph_labels = 
                    CASE 
                        WHEN NOT $graph_label IN r.graph_labels THEN r.graph_labels + $graph_label
                        ELSE r.graph_labels
                    END
                SET r.weight = $weight, r.sentiment = $sentiment
                """,
                source=source, target=target, weight=weight, sentiment=sentiment, graph_label=graph_label+"_posts"
            )
    driver.close()
    print(f"Graph '{graph_label}' added to Neo4j successfully.")

# ----------------------------
# Function to get top-K nodes by PageRank with average sentiment
# ----------------------------
def get_top_k_nodes_with_avg_sentiment_by_pagerank(graph_label: str, k: int = 10):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DATABASE) as session:
        projection_name = f"userGraph_{graph_label}"
        print(f"Projection Name: {projection_name}, Graph Label: {graph_label}")
        
        create_graph_query = """
        CALL gds.graph.project.cypher(
            $projection_name,
            'MATCH (n:User) WHERE $graph_label IN n.graph_labels RETURN id(n) AS id',
            'MATCH (n:User)-[r:MENTIONS]->(m:User) WHERE $graph_label IN r.graph_labels RETURN id(n) AS source, id(m) AS target',
            {parameters: {graph_label: $graph_label}}
        )
        """
        try:
            session.run(create_graph_query, projection_name=projection_name, graph_label=graph_label)
        except Exception as e:
            print(f"Error creating graph projection: {e}")
            return []
        
        page_rank_query = """
        CALL gds.pageRank.stream($projection_name)
        YIELD nodeId, score
        WITH gds.util.asNode(nodeId) AS user, score
        OPTIONAL MATCH (other:User)-[r:MENTIONS]->(user)
        WHERE $graph_label IN r.graph_labels
        WITH user, score, coalesce(avg(r.sentiment), 0) AS avgSentiment, coalesce(avg(r.weight), 0) AS avgWeight
        RETURN user.screen_name AS screen_name, score, avgSentiment, avgWeight
        ORDER BY score DESC
        LIMIT $k
        """
        try:
            result = session.run(page_rank_query, projection_name=projection_name, graph_label=graph_label, k=k)
            top_nodes = [record.data() for record in result]
        except Exception as e:
            print(f"Error running PageRank: {e}")
            top_nodes = []
        
        drop_graph_query = "CALL gds.graph.drop($projection_name)"
        try:
            session.run(drop_graph_query, projection_name=projection_name)
        except Exception as e:
            print(f"Error dropping graph projection: {e}")
            
    driver.close()
    return top_nodes

# ----------------------------
# Endpoints
# ----------------------------

@app.post("/create-graph")
async def create_and_add_graph(request: GraphRequest):
    # try:
    G, twitter_df = create_graph(request.coin_id, request.date_from)
    graph_label = request.graph_label
    add_networkx_graph_to_neo4j(G, graph_label)
    
    # Record each tweet's message_id as processed in Redis
    for tweet_id in twitter_df['message_id']:
        store_processed_tweet(tweet_id, request.coin_id)
    
    return {"message": f"Graph '{graph_label}' created and added to Neo4j successfully."}
    # except Exception as e:
        # raise HTTPException(status_code=500, detail=str(e))

@app.post("/top-k-pagerank")
async def top_k_pagerank(request: TopKRequest):
    try:
        top_nodes = get_top_k_nodes_with_avg_sentiment_by_pagerank(f"{request.graph_label}_posts", request.k)
        return {f"top_{request.k}_nodes": top_nodes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------
# New endpoint for incremental tweet updates
# ----------------------------
class TweetRequest(BaseModel):
    message_id: str  # Unique tweet identifier
    full_text: str
    author_screen_name: str
    stats: dict  # e.g., {'likes': 10, 'retweets': 2, 'replies': 1, 'quotte': 0}

from pydantic import BaseModel

class TweetsByDateRequest(BaseModel):
    date_from: str  # дата в формате ISO или другом, подходящем для вашего проекта
    coin_id: str    # идентификатор монеты (если используется для фильтрации)

@app.post("/add-tweets-by-date")
async def add_tweets_by_date(request: TweetsByDateRequest):
    """
    Эндпоинт для пакетного обновления графа на основе твитов, начиная с указанной даты.
    Извлекаются новые твиты из PostgreSQL, вычисляются sentiment, упоминания и вес,
    а затем данные добавляются в Neo4j. Идентификаторы обработанных твитов сохраняются в Redis.
    """
    try:
        # Извлекаем данные твитов, опубликованных после request.date_from для указанной монеты
        tqdm.pandas()  # Enable progress_apply for pandas
        twitter_df = get_coin_data(request.coin_id, request.date_from)
        if twitter_df.empty:
            return {"message": "Новых твитов не найдено."}
        
        # Обогащаем данные: извлекаем лайки, реплаи, ретвиты, квоты, упоминания и sentiment
        twitter_df['likes'] = twitter_df['stats'].progress_apply(extract_likes)
        twitter_df['replies'] = twitter_df['stats'].progress_apply(extract_reply)
        twitter_df['retweets'] = twitter_df['stats'].progress_apply(extract_retweet)
        twitter_df['quottes'] = twitter_df['stats'].progress_apply(extract_quotte)
        twitter_df['mentions'] = twitter_df['full_text'].progress_apply(extract_mentions)
        twitter_df['sentiment'] = twitter_df['full_text'].progress_apply(analyze_sentiment)
        
        # Формируем метку графа: например, "tweets_{coin_id}"
        graph_label = f"{request.coin_id}"
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        with driver.session(database=NEO4J_DATABASE) as session:
            with session.begin_transaction() as tx:
                for _, row in twitter_df.iterrows():
                    tweet_id = row['message_id']
                    # Пропускаем уже обработанные твиты
                    if is_tweet_processed(tweet_id, request.coin_id):
                        continue
                    
                    author = row['author_screen_name']
                    mentions = row['mentions']
                    sentiment = row['sentiment']
                    # Рассчитываем суммарный вес (если он равен 0 – ставим минимум 1)
                    weight = row['likes'] + row['retweets'] + row['replies'] + row['quottes']
                    if weight == 0:
                        weight = 1
                    
                    # Обеспечиваем существование автора с нужной меткой
                    tx.run(
                        """
                        MERGE (u:User {screen_name: $screen_name})
                        ON CREATE SET u.graph_labels = [$graph_label]
                        ON MATCH SET u.graph_labels =
                            CASE
                                WHEN NOT $graph_label IN u.graph_labels THEN u.graph_labels + $graph_label
                                ELSE u.graph_labels
                            END
                        """,
                        screen_name=author,
                        graph_label=graph_label+"_posts"
                    )
                    
                    # Обрабатываем каждое упоминание в твите
                    for mention in mentions:
                        # Обеспечиваем существование пользователя, на которого ссылаются
                        tx.run(
                            """
                            MERGE (u:User {screen_name: $screen_name})
                            ON CREATE SET u.graph_labels = [$graph_label]
                            ON MATCH SET u.graph_labels =
                                CASE
                                    WHEN NOT $graph_label IN u.graph_labels THEN u.graph_labels + $graph_label
                                    ELSE u.graph_labels
                                END
                            """,
                            screen_name=mention,
                            graph_label=graph_label+"_posts"
                        )
                        # Добавляем или обновляем ребро MENTIONS между автором и упомянутым пользователем
                        tx.run(
                            """
                            MATCH (a:User {screen_name: $source}), (b:User {screen_name: $target})
                            MERGE (a)-[r:MENTIONS]->(b)
                            ON CREATE SET r.weight = $weight,
                                          r.sentiment_sum = $sentiment,
                                          r.count = 1,
                                          r.sentiment = $sentiment,
                                          r.graph_labels = [$graph_label]
                            ON MATCH SET r.weight = r.weight + $weight,
                                         r.sentiment_sum = r.sentiment_sum + $sentiment,
                                         r.count = r.count + 1,
                                         r.sentiment = r.sentiment_sum / r.count,
                                         r.graph_labels =
                                            CASE
                                                WHEN NOT $graph_label IN r.graph_labels THEN r.graph_labels + $graph_label
                                                ELSE r.graph_labels
                                            END
                            """,
                            source=author,
                            target=mention,
                            weight=weight,
                            sentiment=sentiment,
                            graph_label=graph_label+"_posts"
                        )
                    
                    # Отмечаем твит как обработанный
                    store_processed_tweet(tweet_id, request.coin_id)
                tx.commit()
        driver.close()
        return {"message": f"Твиты, опубликованные с {request.date_from}, успешно добавлены и граф обновлён."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------
# Run the service
# ----------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
