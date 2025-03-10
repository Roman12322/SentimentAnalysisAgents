# Whitepaper Documentation for AI Agent Service

Here's tree structure of project
```markdown
.
├── notebooks/
│   ├── engagement_and_growth_rate.ipynb
│   └── GraphStats.ipynb
├── tools/
│   ├── graph_api.py
│   └── graph_tool.py
├── scripts/
│   ├── get_top_k.sh
│   ├── get_summary.sh
│   └── create_graph.sh
├── data/
│   ├── arb.csv
│   ├── usdc_tw.csv
│   ├── link_tw.csv
│   ├── rndr_tw.csv
│   ├── weth_tw.csv
│   ├── tko.csv
│   ├── uni_tw.csv
│   ├── floki.csv
│   ├── enj.csv
│   ├── fdusd_tw.csv
│   └── shib_tw.csv
├── requests_and_responses.py
├── crew.py
├── .env
├── config.py
├── main.py
└── settings/
    ├── .ipynb_checkpoints/
    ├── tasks.yaml
    └── agents.yaml
```

## 1. Overview

The AI Agent Service is a sophisticated system designed to leverage AI agents for retrieving and analyzing graph-based data. The service integrates with a Neo4j database and provides a core API for graph creation and analysis. AI agents utilize these APIs to perform tasks such as identifying influential nodes (users) in a graph using metrics like **PageRank**, **AvgSentiment**, **AvgWeight**. This whitepaper outlines the architecture, functionality, and usage of the service, with a focus on its metrics, tools, and workflows.

---

## 2. Metrics

### PageRank: A Key Metric for Graph Analysis

**PageRank** is an algorithm used to measure the importance or influence of nodes in a graph. Originally developed by Google founders Larry Page and Sergey Brin, it is widely used in network analysis to rank nodes based on their connectivity and the quality of their connections.

#### PageRank Formula

The PageRank score for a node $v$ is calculated iteratively using the following formula:
$$
PR(v) = \frac{1-d}{N} + d \sum_{u \in M(v)} \frac{PR(u)}{L(u)}
$$
Where:
- $PR(v)$ : PageRank score of node $ v $.
- $d$ : Damping factor (typically set to 0.85), representing the probability of continuing to follow links in the graph.
- $N$: Total number of nodes in the graph.
- $M(v)$: Set of nodes that link to node $v$.
- $L(u)$: Number of outgoing links from node $u$.

### AvgSentiment: A Key Metric for Analyzing comminity mood

**AvgSentiment** is a metric that describe how positive/negative messages were **on average**, so if message was truly negative/positive it will be in interval [-1; 1] resprectivly. According this, we developed algorithm that measures AvgSentiment for each node (user) in our graph. 

### AvgWeight

**AvgWeight** as well as AvgSentiment measures **on average** WIEGHT for each node. We describe WIEGHT as a sum of likes, retweets, forwards, replies for each message where user was mentioned. $$Weight = Message(likes, retweets, forwards, replies)$$ This helps us to get more insight about users' activity and what kind of activity is that. 

#### Interpretation
- A higher PageRank score indicates a more influential or important node in the graph.
- The algorithm considers both the number of incoming links (in-degree) and the quality of those links (PageRank of the linking nodes).

In the context of this service, the `/top-k-pagerank` endpoint uses this formula to retrieve the top-k most influential users in a graph.
Below is example of output:

```
{"top_10_nodes":
[
{"screen_name":"sergeynazarov","score":4.080946862792141,"avgSentiment":0.3879870101809502,"avgWeight":279.58333333333337},{"screen_name":"chainlink","score":2.8760013280932526,"avgSentiment":0.3978866098655594,"avgWeight":104.25},{"screen_name":"chainlinkgod","score":2.1555234163116492,"avgSentiment":0.43702547550201415,"avgWeight":166.8},{"screen_name":"arijuels","score":1.278588795526747,"avgSentiment":0.43523670236269635,"avgWeight":216.33333333333334},{"screen_name":"21co__","score":0.9897622719201069,"avgSentiment":0.3427312672138214,"avgWeight":360.0},
{"screen_name":"thergdev","score":0.9897622719201069,"avgSentiment":0.45477698743343353,"avgWeight":264.0},{"screen_name":"cryptexfinance","score":0.9897622719201069,"avgSentiment":0.27842220664024353,"avgWeight":575.5},{"screen_name":"swellnetworkio","score":0.9897622719201069,"avgSentiment":0.2662444934248924,"avgWeight":581.0},{"screen_name":"lukeyoungblood","score":0.9612404689154856,"avgSentiment":0.3976626396179199,"avgWeight":45.0},{"screen_name":"lemiscate","score":0.9612404689154856,"avgSentiment":0.26390203833580017,"avgWeight":68.0}]}
}
```

## 3. Architecture

The AI Agent Service is built on a modular architecture, with each component playing a specific role in the system. Below is a breakdown of the architecture:

### 3.1 Configuration (if you have error, check creds - they must be updated every 3 days)
The `config.py` file contains system variables such as URLs and HTTP settings for connecting to the Neo4j database. These configurations ensure seamless communication between the service and the database. The `config.py` file is critical for setting up the service. It includes:
- **Neo4j Database URLs**: Specifies the connection details for the Neo4j database.
- **HTTP Settings**: Configures the HTTP parameters for API communication.

### 3.2 Tools
The `tools` directory houses the core functionality of the service:
- **graph_api.py**: Defines the API endpoints (`/create_graph` and `/top-k-pagerank`) for graph creation and analysis.
- **graph_tool.py**: Provides a higher-level interface for interacting with the API, simplifying tasks like fetching top-k PageRank users.

## 3.3. API Endpoints

The core API provides two key endpoints for graph analysis:

### 3.3.1 `/create_graph`
This endpoint creates a graph based on the provided data. It processes input datasets (e.g., CSV files) and constructs a graph structure stored in the Neo4j database.

### 3.3.2 `/top-k-pagerank`
This endpoint retrieves the top-k users based on their PageRank scores. It uses the PageRank formula to identify the most influential nodes in the graph.

### 3.3.2 For Runnning API use this: `python graph_api.py`

## 3.4. Graph Tools

The `graph_tool.py` file simplifies interactions with the API. Key functionalities include:
- Fetching top-k PageRank users.
- Providing a user-friendly interface for AI agents to perform graph-related tasks.


### 3.5 Settings
The `settings` directory contains YAML files:
- **tasks.yaml**: Defines the tasks that AI agents can perform.
- **agents.yaml**: Describes the backstory and configuration of each AI agent.

### 3.6 Crew Logic
The `crew.py` file orchestrates the workflow of AI agents, defining how they communicate and execute tasks. The `crew.py` file defines the workflow and tasks for AI agents. It includes:
- **Task Definitions**: Specifies the tasks each agent is responsible for.
- **Communication Logic**: Orchestrates interactions between agents to ensure efficient task execution.

### 3.7 Entry Point
The `main.py` file serves as the user entry point, initializing the service and providing an interface for task execution and data retrieval. The `main.py` file is the gateway for users to access the service. It provides:
- **Task Execution**: Allows users to trigger specific tasks performed by AI agents.
- **Data Retrieval**: Enables users to fetch and view the results of graph analyses.

#### For running: `python main.py`


## 4. Data

Using connection string this script extracts data from Postgres harvester, in this case we get columns: {full_text, stats, create_at, published_at, updated_at, screen_name, coin_id}.


## 5. Conclusion

The AI Agent Service is a powerful platform for graph-based data retrieval and analysis. By leveraging AI agents, a core API, and a Neo4j database, the service provides users with tools to identify influential nodes, create graphs, and perform complex analyses. The integration of metrics like PageRank ensures accurate and insightful results, making the service an invaluable asset for data-driven decision-making.

---

This whitepaper provides a detailed overview of the AI Agent Service, its architecture, and its functionalities. For further information or support, please refer to the official documentation or contact the support team.
