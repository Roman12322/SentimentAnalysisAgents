from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from tools.graph_tool import CoinTransactionsSearchTool, CoinSentimentSearchTool, CoinXPostsRetrieveTool, CoinTransactionsRetrieveTool, CoinPricesRetrieveTool
from dotenv import load_dotenv

load_dotenv()


@CrewBase
class AIsigts:
    """AIsigts crew"""

    agents_config = 'settings/agents.yaml'
    tasks_config = 'settings/tasks.yaml'
    
    @agent
    def data_sentiment_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['data_sentiment_retriever'],
            tools=[CoinSentimentSearchTool()],
            verbose=True
        )

    @agent
    def data_transactions_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['data_transactions_retriever'],
            tools=[CoinTransactionsSearchTool()],
            verbose=True
        )

    @agent
    def data_twitter_posts_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['data_twitter_posts_retriever'],
            tools=[CoinXPostsRetrieveTool()],
            verbose=True
        )

    @agent
    def data_sql_transactions_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['data_sql_transactions_retriever'],
            tools=[CoinTransactionsRetrieveTool()],
            verbose=True
        )

    @agent
    def data_sql_prices_retriever(self) -> Agent:
        return Agent(
            config=self.agents_config['data_sql_prices_retriever'],
            tools=[CoinPricesRetrieveTool()],
            verbose=True
        )
    
    @agent
    def crypto_expert(self) -> Agent:
        return Agent(
            config=self.agents_config['crypto_expert'],
            tools=[],
            verbose=True
        )
    
    @task
    def retrieve_data_sentiment_task(self) -> Task:
        return Task(
            config=self.tasks_config['retrieve_data_sentiment_task'],
        )

    @task
    def retrieve_data_transactions_task(self) -> Task:
        return Task(
            config=self.tasks_config['retrieve_data_transactions_task'],
        )
        
    @task
    def retrieve_twitter_posts_task(self) -> Task:
        return Task(
            config=self.tasks_config['retrieve_twitter_posts_task'],
        )

    @task
    def retrieve_sql_data_transactions_task(self) -> Task:
        return Task(
            config=self.tasks_config['retrieve_sql_data_transactions_task'],
        )

    @task
    def retrieve_sql_data_prices_task(self) -> Task:
        return Task(
            config=self.tasks_config['retrieve_sql_data_prices_task'],
        )

    
    @task
    def summary_task(self) -> Task:
        return Task(
            config=self.tasks_config['summary_task'],
        )
    
    @crew
    def crew(self) -> Crew:
        """Creates the AIsigts crew"""
        return Crew(
            agents=self.agents,  # Automatically created by the @agent decorator
            tasks=self.tasks,    # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
            # process=Process.hierarchical,  # In case you want to use that instead
        )
