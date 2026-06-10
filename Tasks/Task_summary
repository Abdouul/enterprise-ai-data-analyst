 Overview
For your final project, you will step out of the sandbox and architect a production-grade Generative AI system. You are tasked with building a Multi-Modal Enterprise Agent—an autonomous AI analyst capable of answering complex business questions by navigating both unstructured documents (PDFs/Reports) and structured relational databases (SQL).
This project is due 14 days after the final class. It will serve as a capstone piece for your engineering portfolio.
Deadline (no extension): Sunday, June 14 at 23:59.
🏢 The Scenario
You are the Lead AI Data Engineer at a financial tech startup. Non-technical executives need to ask questions like:
"What was Apple's total hardware revenue last year, and what did their Q3 report say about supply chain risks?"
A standard LLM cannot answer this. It requires an agent that can dynamically write SQL to calculate the revenue, and simultaneously query a Vector Database to read the Q3 report.

## 🏗️ Core Requirements & Deliverables

You must build and submit a GitHub repository containing the following four architectural phases:

### Phase 1: The Vector ETL Pipeline (Data Engineering)

- **The Dataset:** Find or create a dataset containing at least 10 complex text documents (e.g., corporate financial reports, technical manuals, or legal contracts).
*Attention*: You need to clean the documents before ingestion.
- **The Pipeline:** Write an automated Python script that parses the text, chunks it semantically (not just fixed-size!), embeds it using a local HuggingFace model (e.g., `all-MiniLM`), and inserts it into a **Dockerized Vector Database** (Qdrant, Milvus, or pgvector).
- **Crucial:** You must attach structured JSON metadata (e.g., `company_name`, `document_year`) to every vector.

### Phase 2: The Agentic State Machine (AI Engineering)

- Use **LangGraph** to build a ReAct Agent.
- **Tool 1 (`execute_sql`):** The agent must be able to query a local SQLite database containing structured numerical data. (Include the error-recovery loop you learned in Lab 4).
- **Tool 2 (`search_vector_db`):** The agent must be able to search your Vector Database. It should use `Instructor` / Pydantic to extract strict metadata filters from the user's query *before* executing the semantic search.

### Phase 3: Cloud Deployment & FinOps (Cloud Computing)

- **Containerization:** Write a `Dockerfile` that packages your LangGraph agent and exposes it as a FastAPI REST endpoint.
- **Cloud Run:** Deploy this container to **Google Cloud Run** using your GCP Free Credits. (This demonstrates Serverless AI architecture).
- **FinOps Tracking:** Your API must calculate and log the exact Token Cost of every agentic loop execution in the terminal/logs.

### Phase 4: The Architecture Report (Evaluation)

Submit a 2-3 page Markdown (`REPORT.md`) document containing:

1. **System Architecture Diagram:** A visual flow of your ETL pipeline and Agentic graph.
2. **RAGAS Evaluation:** Write a short script that runs 5 test queries through your deployed agent. Manually grade the outputs for **Faithfulness** (no hallucinations) and **Answer Relevance**.
3. **Cost Analysis:** A breakdown of how many GCP credits were consumed and the cost per 100 queries.

## The "Extra Mile" (Advanced Openings)

If you want to achieve the highest possible grade (and build a truly senior-level portfolio project), implement **at least one** of these advanced, bleeding-edge architectures:

- **Advanced Option 1: GraphRAG Integration (Neo4j)**
Instead of a standard Vector DB, deploy a local Neo4j container. Write an ETL script that uses an LLM to extract Entities (Nodes) and Relationships (Edges) from your text, allowing the agent to execute complex multi-hop Graph queries (Cypher) alongside vector search.
- **Advanced Option 2: Semantic Caching (Redis)**
Agent loops are slow and expensive. Implement a Semantic Cache using Redis. If User B asks a question that has a 95% cosine similarity to a question User A asked yesterday, bypass the LangGraph agent entirely and instantly return the cached answer.
- **Advanced Option 3: Bare-Metal Open-Weight Serving (vLLM)**
Instead of using the Gemini or OpenAI API for your agent, use your GCP credits to spin up a Compute Engine Deep Learning VM (L4 or T4 GPU). Deploy **vLLM**, host an open-source model (e.g., `Llama-3-8B-Instruct`), and point your LangGraph agent to your own private, self-hosted inference engine.

## Submission Guidelines

1. **GitHub URL:** Your repository must be **public**. It must contain the `README.md` with instructions on how to start the Docker containers and run the code.
2. **Live Endpoint / Demo:** Provide the Google Cloud Run URL, OR a 3-minute Loom/YouTube video demonstrating the agent successfully running and recovering from an error.
3. **Clean Code:** Do not commit your `.env` files or API keys. Use `.gitignore`.
4. **Online Presentation**: An online presentation will be fixed with each team. Time allowed for the presentation is 5 minutes followed by questions to each member (you are responsible for the code you provide). 

*Good luck. You are no longer just calling APIs; you are architecting autonomous AI systems.*