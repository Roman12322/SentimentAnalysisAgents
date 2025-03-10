from pydantic import BaseModel


class GraphRequest(BaseModel):
    coin_id: str
    date_from: str
    graph_label: str  # Новое поле для идентификации графа

class TopKRequest(BaseModel):
    graph_label: str  # Граф, для которого рассчитывается PageRank
    k: int

# --------------------------------------------------
# Определение моделей запросов для инкрементального обновления транзакций
# --------------------------------------------------

class TransactionRequest(BaseModel):
    contact_address: str
    from_address: str
    to_address: str
    value: float
    timestamp: str  # Ожидается формат ISO или аналогичный
    network_id: str
    coin_id: str  # Имя монеты