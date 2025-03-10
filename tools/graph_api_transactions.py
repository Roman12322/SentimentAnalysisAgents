from fastapi import FastAPI, HTTPException
import uvicorn
import networkx as nx
from pydantic import BaseModel
from typing import List
from requests_and_responses import GraphRequest, TopKRequest, TransactionRequest  # These models are defined in your project
from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE, CONNECTION_STRING
import re
from tqdm import tqdm
from neo4j import GraphDatabase
import pandas as pd
import psycopg2
import redis

# --------------------------------------------------
# Initialize FastAPI and Redis client for deduplication
# --------------------------------------------------
app = FastAPI()
redis_client = redis.Redis(host='localhost', port=26379, db=0)

# --------------------------------------------------
# Helper functions for transaction deduplication using Redis
# --------------------------------------------------
def store_processed_transaction(tx_id: str, coin_id: str = ""):
    key = f"processed_transactions:{coin_id}" if coin_id else "processed_transactions"
    redis_client.sadd(key, tx_id)

def is_transaction_processed(tx_id: str, coin_id: str = "") -> bool:
    key = f"processed_transactions:{coin_id}" if coin_id else "processed_transactions"
    return redis_client.sismember(key, tx_id)

# --------------------------------------------------
# Функция получения данных о транзакциях из PostgreSQL
# --------------------------------------------------
def get_coin_data(coin_id: str, data_from: str):
    # Note: We now select tx_id as a unique identifier (assumed to be present in the erc20_transfer table)
    query = f"""
    SELECT * FROM ratex.public.erc20_transfer et 
    INNER JOIN coin_network 
      ON coin_network.contract_address = et.contract_address 
         AND coin_network.coin_id = '{coin_id}'
    WHERE et."timestamp" > '{data_from}'
    """
    conn_str = "postgresql://rxd104:gKHUT2puBohzhY9mrcoy5kEE@157.90.4.114:5432/ratex"
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    cur.execute(query)
    dataset = cur.fetchall()
    conn.close()

    # Mapping the returned columns to a dict.
    data = [{
        'tx_id': item[4]+item[5],
        'contact_address': item[0],
        'from_address': item[1],
        'to_address': item[2],
        'value': float(item[3]),
        'timestamp': item[-1],
        'coin_id': coin_id
    } for item in dataset]
    
    df = pd.DataFrame(data)
    return df

# --------------------------------------------------
# Функция создания графа (NetworkX) на основе данных транзакций
# --------------------------------------------------
def create_graph(coin_id: str, data_from: str):
    """
    Получает данные о транзакциях, строит направленный граф (DiGraph) с узлами-адресами.
    Ребра (TRANSACTION) имеют следующие свойства:
      - contact_address, value, timestamp, contact_address, coin_id.
    """
    tx_df = get_coin_data(coin_id, data_from)
    tqdm.pandas()  # Для отображения progress_apply при необходимости

    # Создаем направленный граф
    G = nx.DiGraph()
    for _, row in tx_df.iterrows():
        source = row['from_address']
        target = row['to_address']
        value = row['value']
        if value == 0:
            value = 1  # Задаем минимальное значение, если 0
        G.add_edge(source, target, 
                   contact_address=row['contact_address'],
                   value=value,
                   timestamp=row['timestamp'],
                   coin_id=row['coin_id'])
    return G, tx_df

# --------------------------------------------------
# Функция для добавления NetworkX-графа в Neo4j
# --------------------------------------------------
def add_networkx_graph_to_neo4j(G: nx.DiGraph, graph_label: str):
    """
    Итерируется по узлам и ребрам графа и добавляет/обновляет данные в Neo4j.
    Каждый узел (адрес) получает label User, а также обновляется массив graph_labels.
    Ребра TRANSACTION получают свойства транзакции и список graph_labels.
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DATABASE) as session:
        # Добавляем/обновляем узлы
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
                """, screen_name=node, graph_label=graph_label+"_transactions")
        # Добавляем/обновляем транзакционные ребра
        for source, target, data in G.edges(data=True):
            session.run(
                """
                MATCH (a:User {screen_name: $source}), (b:User {screen_name: $target})
                MERGE (a)-[r:TRANSACTION]->(b)
                ON CREATE SET r.graph_labels = [$graph_label]
                ON MATCH SET r.graph_labels = 
                    CASE 
                        WHEN NOT $graph_label IN r.graph_labels THEN r.graph_labels + $graph_label
                        ELSE r.graph_labels
                    END
                SET r.contact_address = $contact_address,
                    r.value = $value,
                    r.timestamp = $timestamp,
                    r.coin_id = $coin_id
                """,
                source=source,
                target=target,
                contact_address=data.get('contact_address'),
                value=data.get('value'),
                timestamp=data.get('timestamp'),
                coin_id=data.get('coin_id'),
                graph_label=graph_label+"_transactions"
            )
    driver.close()
    print(f"Graph '{graph_label}' added to Neo4j successfully.")

# --------------------------------------------------
# Функция обновления метрик для транзакционных узлов
# --------------------------------------------------
def update_transaction_metrics(graph_label: str):
    """
    Для всех узлов (User), у которых в массиве graph_labels присутствует нужный graph_label,
    вычисляются:
      - in_tx_count: количество входящих транзакций
      - out_tx_count: количество исходящих транзакций
      - balance: сумма входящих значений минус сумма исходящих
      - transaction_percentage: (in_tx_count + out_tx_count) / (2 * общее число транзакций графа) * 100
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run(
            """
            MATCH (n:User) 
            WHERE $graph_label IN n.graph_labels
            OPTIONAL MATCH (n)<-[in:TRANSACTION]-()
            OPTIONAL MATCH (n)-[out:TRANSACTION]->()
            WITH n, count(in) AS in_tx, count(out) AS out_tx, 
                 coalesce(sum(in.value),0) AS total_in, 
                 coalesce(sum(out.value),0) AS total_out
            SET n.in_tx_count = in_tx,
                n.out_tx_count = out_tx,
                n.balance = total_in - total_out
            """,
            graph_label=graph_label+"_transactions"
        )
        result = session.run(
            """
            MATCH ()-[r:TRANSACTION]->() 
            WHERE $graph_label IN r.graph_labels 
            RETURN count(r) AS total_tx
            """,
            graph_label=graph_label+"_transactions"
        )
        total_tx_record = result.single()
        total_tx = total_tx_record["total_tx"] if total_tx_record is not None else 0
        session.run(
            """
            MATCH (n:User)
            WHERE $graph_label IN n.graph_labels
            SET n.transaction_percentage = CASE 
                WHEN $total_tx = 0 THEN 0 
                ELSE toFloat(n.in_tx_count + n.out_tx_count) / (2.0 * $total_tx) 
                END
            """,
            graph_label=graph_label+"_transactions",
            total_tx=total_tx
        )
    driver.close()
    print(f"Metrics for graph '{graph_label}' updated successfully.")

# --------------------------------------------------
# Функция получения топ-K узлов по алгоритму PageRank с метриками транзакций
# --------------------------------------------------
def get_top_k_nodes_by_pagerank(graph_label: str, k: int = 10):
    """
    Создает проекцию графа (на основе узлов с graph_label), запускает алгоритм PageRank,
    а затем возвращает топ-K узлов с метриками:
      - screen_name, score, in_tx_count, out_tx_count, balance, transaction_percentage.
    После выполнения проекция удаляется.
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    top_nodes = []
    with driver.session(database=NEO4J_DATABASE) as session:
        projection_name = f"userGraph_{graph_label+"_transactions"}"
        print(f"Projection Name: {projection_name}, Graph Label: {graph_label}")
        create_proj_query = """
        CALL gds.graph.project.cypher(
            $projection_name,
            'MATCH (n:User) WHERE $graph_label IN n.graph_labels RETURN id(n) AS id',
            'MATCH (n:User)-[r:TRANSACTION]->(m:User) WHERE $graph_label IN r.graph_labels RETURN id(n) AS source, id(m) AS target',
            { parameters: { graph_label: $graph_label } }
        )
        """
        try:
            session.run(create_proj_query, projection_name=projection_name, graph_label=graph_label)
        except Exception as e:
            print(f"Error creating graph projection: {e}")
            return []
        
        page_rank_query = """
        CALL gds.pageRank.stream($projection_name)
        YIELD nodeId, score
        WITH gds.util.asNode(nodeId) AS user, score
        RETURN user.screen_name AS screen_name, score, 
               user.in_tx_count AS in_tx_count, 
               user.out_tx_count AS out_tx_count,
               user.balance AS balance,
               user.transaction_percentage AS transaction_percentage
        ORDER BY score DESC
        LIMIT $k
        """
        try:
            result = session.run(page_rank_query, projection_name=projection_name, graph_label=graph_label, k=k)
            top_nodes = [record.data() for record in result]
        except Exception as e:
            print(f"Error running PageRank: {e}")
            top_nodes = []
        
        drop_query = "CALL gds.graph.drop($projection_name)"
        try:
            session.run(drop_query, projection_name=projection_name)
        except Exception as e:
            print(f"Error dropping graph projection: {e}")
    driver.close()
    return top_nodes

# --------------------------------------------------
# Эндпоинты сервиса
# --------------------------------------------------

@app.post("/create-graph")
async def create_and_add_graph(request: GraphRequest):
    """
    Эндпоинт для создания графа транзакций.
    Используя coin_id и дату (date_from) из запроса,
    строится NetworkX-граф, который затем добавляется в Neo4j с dynamic label.
    После этого обновляются метрики узлов, и все транзакционные ID сохраняются в Redis.
    """
    # try:
    G, tx_df = create_graph(request.coin_id, request.date_from)
    graph_label = f"transactions_{request.coin_id}"
    add_networkx_graph_to_neo4j(G, graph_label)
    update_transaction_metrics(graph_label)
    
    # Сохраняем все transaction ID в Redis для дедупликации
    for tx_id in tx_df['tx_id']:
        store_processed_transaction(tx_id, request.coin_id)
        
    return {"message": f"Graph '{graph_label}' created and added to Neo4j successfully."}
    # except Exception as e:
        # raise HTTPException(status_code=500, detail=str(e))

@app.post("/top-k-pagerank")
async def top_k_pagerank(request: TopKRequest):
    """
    Эндпоинт для получения топ-K узлов по алгоритму PageRank с вычисленными метриками транзакций.
    """
    try:
        top_nodes = get_top_k_nodes_by_pagerank(f"transactions_{request.graph_label}_transactions", request.k)
        return {f"top_{request.k}_nodes": top_nodes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



from pydantic import BaseModel

class TransactionByDateRequest(BaseModel):
    date_from: str  # ISO-формат или другой, подходящий для вашего запроса
    coin_id: str    # если нужно указать, для какой монеты брать данные

@app.post("/add-transactions-by-date")
async def add_transactions_by_date(request: TransactionByDateRequest):
    """
    Эндпоинт для инкрементального добавления транзакций, начиная с указанной даты.
    Принимается только дата (и coin_id), а данные транзакций извлекаются из PostgreSQL.
    """
    try:
        # Получаем транзакции, начиная с указанной даты для нужной монеты
        tx_df = get_coin_data(request.coin_id, request.date_from)
        if tx_df.empty:
            return {"message": "Новых транзакций не найдено."}
        
        graph_label = f"transactions_{request.coin_id}"
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        with driver.session(database=NEO4J_DATABASE) as session:
            with session.begin_transaction() as tx:
                for _, row in tx_df.iterrows():
                    # Если транзакция уже обработана, пропускаем её
                    if is_transaction_processed(row['tx_id'], request.coin_id):
                        continue
                    
                    # Создаём или ищем узел отправителя
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
                        screen_name=row['from_address'],
                        graph_label=graph_label
                    )
                    # Создаём или ищем узел получателя
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
                        screen_name=row['to_address'],
                        graph_label=graph_label
                    )
                    # Создаём ребро TRANSACTION
                    tx.run(
                        """
                        MATCH (a:User {screen_name: $from_address}), (b:User {screen_name: $to_address})
                        CREATE (a)-[:TRANSACTION {
                            contact_address: $contact_address,
                            value: $value,
                            timestamp: $timestamp,
                            coin_id: $coin_id,
                            graph_labels: [$graph_label]
                        }]->(b)
                        """,
                        from_address=row['from_address'],
                        to_address=row['to_address'],
                        contact_address=row['contact_address'],
                        value=row['value'],
                        timestamp=row['timestamp'],
                        coin_id=row['coin_id'],
                        graph_label=graph_label
                    )
                    # Отмечаем транзакцию как обработанную
                    store_processed_transaction(row['tx_id'], request.coin_id)
                tx.commit()
        driver.close()
        # Обновляем метрики для узлов данного графа
        update_transaction_metrics(graph_label)
        return {"message": f"Транзакции с {request.date_from} успешно добавлены и граф обновлён."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# --------------------------------------------------
# Запуск сервиса
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
