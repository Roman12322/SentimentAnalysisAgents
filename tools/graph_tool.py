from typing import Any, Optional, Type
from pydantic import BaseModel, Field
import requests
from crewai.tools import BaseTool
from config import BASE_URL_SENTIMENT, TOKEN, BASE_URL_TRANSACTIONS, CONNECTION_STRING, CONNECTION_STRING_transactions, CONNECTION_STRING_prices
import json
from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel
from typing import List
from requests_and_responses import GraphRequest, TopKRequest
from neo4j import GraphDatabase
import json
import pandas as pd
from tqdm import tqdm
import psycopg2
# Enable the tqdm progress bar for pandas
tqdm.pandas()

class CoinSentimentSearchToolInput(BaseModel):
    coin_sentiment_name: str = Field(..., description='name of coin')
    k_retrieved_users: int = Field(..., description='number of retrieved users')
    
class CoinSentimentSearchTool(BaseTool):
    name: str = 'Coin search tool'
    description: str = 'Searches top-k valueable nodes in graph'
    args_schema: Type[BaseModel] = CoinSentimentSearchToolInput

    def __init__(self):
        super().__init__()

    def get_top_k_nodes(self, coin_sentiment_name: str, k_retrieved_users: int) -> dict :
        """
        Calls the /top-k-pagerank endpoint with the required payload.
        """
        url = f"{BASE_URL_SENTIMENT}/top-k-pagerank"
        payload = {
            "graph_label": coin_sentiment_name.strip(),  # This should match the graph_label you used earlier
            "k": k_retrieved_users                         # Number of top nodes to return
        }
        headers = {"Content-Type": "application/json"}
    
        try:
            response = requests.post(url, json=payload, headers=headers).json()[f'top_{k_retrieved_users}_nodes']
            return response
        except requests.exceptions.RequestException as e:
            print("Error calling /top-k-pagerank:", e)

    def _run(self, coin_sentiment_name: str, k_retrieved_users: int) -> str : 
    
        users_stats = self.get_top_k_nodes(coin_sentiment_name, k_retrieved_users)
        return users_stats


class CoinXPostsRetrieveToolInput(BaseModel):
    coin_name: str = Field(..., description='name of coin')
    k_rows: int = Field(..., description='number of retrieved users')
    current_date: str = Field(..., description='current datetime')
    
class CoinXPostsRetrieveTool(BaseTool):
    name: str = 'Coin Twitter posts retrieve tool'
    description: str = 'Searches last k-rows in table of transactions'
    args_schema: Type[BaseModel] = CoinXPostsRetrieveToolInput

    def __init__(self):
        super().__init__()

    def get_last_k_rows(self, coin_name: str, k_rows: int, current_date: str) -> dict :
        """
        Get last k-rows from harvester
        """
        query = f"""
        select tp.author_screen_name, tp.stats, tp.full_text 
        from tw_post tp
        inner join tw_channel_coin tcc on tp.channel_id=tcc.channel_id 
        where tcc.coin_id='{coin_name}' and tp.created_at >= '{current_date}'
        LIMIT {k_rows}
        """
        conn_str = CONNECTION_STRING
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        cur.execute(query)
        dataset = cur.fetchall()
        conn.close()
        data = [{'author_screen_name': item[0], 'stats': item[1],'text': item[2]} for item in dataset]
        return data

    def _run(self, coin_name: str, k_rows: int, current_date: str) -> str: 
        posts = self.get_last_k_rows(coin_name, k_rows, current_date)
        return posts

class CoinTransactionsSearchToolInput(BaseModel):
    coin_name: str = Field(..., description='name of coin')
    k_retrieved_users: int = Field(..., description='number of retrieved users')
    
class CoinTransactionsSearchTool(BaseTool):
    name: str = 'Coin transaction search tool'
    description: str = 'Searches top-k valueable nodes in graph'
    args_schema: Type[BaseModel] = CoinTransactionsSearchToolInput

    def __init__(self):
        super().__init__()

    def get_top_k_nodes(self, coin_name: str, k_retrieved_users: int) -> dict :
        """
        Calls the /top-k-pagerank endpoint with the required payload.
        """
        url = f"{BASE_URL_TRANSACTIONS}/top-k-pagerank"
        payload = {
            "graph_label": coin_name,  # This should match the graph_label you used earlier
            "k": k_retrieved_users                         # Number of top nodes to return
        }
        headers = {"Content-Type": "application/json"}
    
        try:
            response = requests.post(url, json=payload, headers=headers).json()[f'top_{k_retrieved_users}_nodes']
            return response
        except requests.exceptions.RequestException as e:
            print("Error calling /top-k-pagerank:", e)

    def _run(self, coin_name: str, k_retrieved_users: int) -> str : 
    
        users_stats = self.get_top_k_nodes(coin_name, k_retrieved_users)
        return users_stats


class CoinTransactionsRetrieveToolInput(BaseModel):
    coin_name: str = Field(..., description='name of coin')
    k_rows: int = Field(..., description='number of retrieved users')
    current_date: str = Field(..., description='current datetime')
    
class CoinTransactionsRetrieveTool(BaseTool):
    name: str = 'Coin transactions retrieve tool'
    description: str = 'Searches last k-rows in table of transactions'
    args_schema: Type[BaseModel] = CoinTransactionsRetrieveToolInput

    def __init__(self):
        super().__init__()

    def get_last_k_rows(self, coin_name: str, k_rows: int, current_date: str) -> dict :
        """
        Get last k-rows from erc20_transfer table of transactions
        """
        query = f"""
        SELECT * FROM ratex.public.erc20_transfer et 
        INNER JOIN coin_network ON coin_network.contract_address = et.contract_address 
            AND coin_network.coin_id = '{coin_name}'
        WHERE et."timestamp" >= '{current_date}'
        ORDER BY et.value DESC
        LIMIT {k_rows}
        """
        conn_str = CONNECTION_STRING_transactions
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        cur.execute(query)
        dataset = cur.fetchall()
        conn.close()
        
        data = []
        for item in dataset:
            record = {
                'from_address': item[1],
                'to_address': item[2],
                'value': item[3],
            }
            data.append(record)
        return data

    def _run(self, coin_name: str, k_rows: int, current_date: str) -> str: 
    
        transactions = self.get_last_k_rows(coin_name, k_rows, current_date)
        return transactions



class CoinPriceRetrieveToolInput(BaseModel):
    coin_name: str = Field(..., description='name of coin')
    
class CoinPricesRetrieveTool(BaseTool):
    name: str = 'Coin price retrieve tool'
    description: str = 'Searches last price in table of coin_prices'
    args_schema: Type[BaseModel] = CoinPriceRetrieveToolInput

    def __init__(self):
        super().__init__()

    def get_last_price(self, coin_name: str) -> dict :
        """
        Get last price x-coin-price aggregated
        """
        query = f"""
        SELECT x.coin_id, x."timestamp", x."interval", x.price_usd
        FROM public.x_coin_price_agg x
        WHERE x.coin_id = '{coin_name}'
        ORDER BY x."timestamp" DESC
        LIMIT 1
        """
        conn_str = CONNECTION_STRING_prices
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        cur.execute(query)
        dataset = cur.fetchall()
        conn.close()
        
        data = []
        for item in dataset:
            record = {
                'value': float(item[3]),
            }
            data.append(record)
        return data

    def _run(self, coin_name: str) -> str: 
    
        prices = self.get_last_price(coin_name)
        return prices


