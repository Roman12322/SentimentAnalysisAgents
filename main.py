#!/usr/bin/env python
import sys
import warnings
from datetime import datetime, timedelta
from crew import AIsigts
from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel
from typing import List
import json
import pandas as pd
import psycopg2  # For PostgreSQL


warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

def run():
    """
    Запускает crew в интерактивном режиме, позволяющем вводить данные бесконечно.
    Для выхода введите 'exit'.
    """
    print("Запуск интерактивного режима. Для выхода введите 'exit'.")
    
    while True:
        coin_name = input("Введите название монеты (coin_name): ")
        if coin_name.lower() == 'exit':
            print("Выход из программы.")
            break
        
        k_value = input("Введите число k_retrieved_users: ")
        if k_value.lower() == 'exit':
            print("Выход из программы.")
            break
        
        try:
            k_retrieved_users = int(k_value)
        except ValueError:
            print("Ошибка: k_retrieved_users должно быть числом. Попробуйте еще раз.\n")
            continue
        
        # Get current time 12 hours ago
        current_time_delay_12h = datetime.now() - timedelta(days=1)
        
        inputs = {
            'coin_name': coin_name,
            'coin_sentiment_name': 'arbitrum',
            'k_retrieved_users': k_retrieved_users,
            'current_date' : current_time_delay_12h.strftime("%Y-%m-%d %H:%M:%S"),
            'k_rows' : 10
        }
        
        # Выполняем crew с введёнными данными
        result = AIsigts().crew().kickoff(inputs=inputs)
        print(result)

if __name__ == "__main__":
    run()
