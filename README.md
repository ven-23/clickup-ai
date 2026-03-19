# ClickUp AI Agent (V40 Overhaul) 🚀

A professional, enterprise-grade AI analytics system for ClickUp time-tracking data. Featuring a **Dockerized** architecture, **FastAPI** backend, **Streamlit** web interface, and **Sentry** observability.

![Status](https://img.shields.io/badge/Status-V40_Production-brightgreen)
![Architecture](https://img.shields.io/badge/Architecture-LangGraph-orange)
![Interface](https://img.shields.io/badge/Interface-Streamlit-red)

## 🌟 V40 Architectural Features
### 1. **Full Dockerization** 🐳
The entire stack (PostgreSQL, FastAPI, and Streamlit) is containerized for one-click deployment.

### 2. **Professional Web UI** 📊
A sleek, interactive chat interface built with **Streamlit** that provides a modern user experience with real-time data visualization.

### 3. **Tiered Model Routing** 🧠
Optimized for performance and cost:
*   **GPT-4o-mini**: Orchestration and fast responses.
*   **GPT-4o**: High-precision SQL generation and complex data reasoning.

### 4. **Sentry Observability** 🔭
Full request tracing and error monitoring enabled. See every logic step and query error in real-time.

---

## 🛠️ Technology Stack
*   **Orchestration**: [LangGraph](https://github.com/langchain-ai/langgraph)
*   **API Framework**: [FastAPI](https://fastapi.tiangolo.com/)
*   **MCP Server**: [FastMCP](https://github.com/lastmile-ai/mcp) (Data Analyst Tools)
*   **Frontend**: [Streamlit](https://streamlit.io/)
*   **Database**: PostgreSQL 16
*   **Observability**: [Sentry](https://sentry.io/)

---

## 🚀 Quick Start (True 100% Docker)

### 1. Environment Setup
Create a `.env` file in the root:
```env
OPENAI_API_KEY=your_openai_key
DB_URL=postgresql://user:pass@localhost:5433/clickup_db
HOST_DATA_PATH="C:/path/to/your/Timesheets"
SENTRY_DSN=your_sentry_dsn

### 2. Launch Everything (Data + API + UI)
Run this single command. It will automatically initialize the database, import your local CSVs, and start the Web UI:
```bash
docker-compose up -d --build
```
> [!NOTE]
> The data import happens automatically via the `import` service, which mounts your local `Timesheets` folder.

### 3. Access the Agent
*   **Web UI**: `http://localhost:8501`
*   **API Docs**: `http://localhost:8000/docs`

---

## 📊 Testing & CI/CD
The project includes a `pytest` suite and is pre-configured with **GitHub Actions** for automated quality assurance on every push.
```bash
pytest tests/
```

---

## 📜 License & Acknowledgments
Built with 🧠 by Antigravity. For organizational data analysis demo.
