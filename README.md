# 🍽️ BiteMate

<div align="center">

**AI-Powered Personalized Meal Planning Assistant**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Google ADK](https://img.shields.io/badge/Google-ADK%201.19-4285F4.svg)](https://github.com/google/adk)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[Features](#-features) •
[Architecture](#-architecture) •
[Installation](#-installation) •
[Usage](#-usage) •
[API Documentation](#-api-documentation) •
[Testing](#-testing)

</div>

---

## 📖 Overview

BiteMate is an intelligent meal planning platform powered by Google's Agentic Development Kit (ADK) and multi-agent AI architecture. It creates personalized meal plans, provides cooking instructions, and offers nutritional guidance based on your lifestyle, dietary preferences, and health goals.

### Key Highlights

- **🤖 Multi-Agent System**: Router → Profiler → Meal Generator orchestration
- **🧠 AI-Powered**: Built on Google Gemini 2.0 Flash for fast, intelligent responses
- **💾 Persistent Memory**: PostgreSQL for user profiles + Pinecone for vector search
- **🔧 MCP Integration**: Model Context Protocol for extensible tool ecosystem
- **🌐 Full-Stack**: FastAPI backend + Streamlit frontend
- **📊 Nutritional Intelligence**: Automatic calorie calculation and meal variety tracking

---

## ✨ Features

### Core Capabilities

- **Intelligent User Profiling**
  - Extract demographic info (age, weight, height, gender)
  - Track health conditions and dietary restrictions
  - Store and recall user preferences

- **Personalized Meal Planning**
  - Recipe recommendations based on user profile
  - Nutritional analysis and calorie calculations
  - Daily meal plan generation (breakfast, lunch, dinner, snacks)
  - Cooking instructions with step-by-step guidance

- **Smart Orchestration**
  - Intent routing (profile update / meal generation / full flow)
  - Context-aware conversation handling
  - Session and memory management

- **Data Persistence**
  - PostgreSQL for structured user data
  - Pinecone vector database for semantic search
  - Session-based chat history

---

## 🏗️ Architecture

### System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                          │
│                    (Streamlit Frontend)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ HTTP
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                          │
│                      (REST API Layer)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   BiteMate Orchestrator                         │
│         ┌───────────────────────────────────────┐               │
│         │       Router Agent                    │               │
│         │   (Intent Classification)             │               │
│         └──────────────┬────────────────────────┘               │
│                        │                                         │
│          ┌─────────────┴─────────────┐                          │
│          ▼                           ▼                          │
│   ┌─────────────┐            ┌──────────────┐                  │
│   │  Profiler   │            │ Meal Generator│                  │
│   │   Agent     │            │     Agent     │                  │
│   └──────┬──────┘            └───────┬───────┘                  │
│          │                           │                          │
│          └──────────┬────────────────┘                          │
│                     │                                            │
└─────────────────────┼────────────────────────────────────────────┘
                      │
        ┌─────────────┴──────────────┐
        │                            │
        ▼                            ▼
┌───────────────┐          ┌──────────────────┐
│   PostgreSQL  │          │     Pinecone     │
│ (User Profiles│          │  (Vector Search) │
│  & Meal Data) │          │                  │
└───────────────┘          └──────────────────┘
```

### Agent Architecture

| Agent | Model | Purpose | Output |
|-------|-------|---------|---------|
| **Router Agent** | Gemini 2.0 Flash | Classify user intent | `UPDATE_PROFILE` / `GENERATE_PLAN` / `FULL_FLOW` |
| **Profiler Agent** | Gemini 2.0 Flash | Extract & store user profile, calculate nutrition | Profile summary |
| **Meal Generator Agent** | Gemini 2.0 Flash | Generate recipes & cooking instructions | Meal plan with recipes |

### Technology Stack

**Backend**
- **Framework**: FastAPI (async REST API)
- **AI/ML**: Google ADK, Gemini 2.0 Flash
- **Databases**: PostgreSQL (structured data), Pinecone (vector embeddings)
- **Tools**: MCP (Model Context Protocol)

**Frontend**
- **Framework**: Streamlit
- **HTTP Client**: Requests

**DevOps**
- **Package Management**: UV / pip
- **Testing**: pytest, pytest-asyncio
- **Code Quality**: black, ruff, mypy
- **Environment**: python-dotenv

---

## 🚀 Installation

### Prerequisites

- Python 3.10 or higher
- PostgreSQL (for user data)
- Pinecone account (for vector search)
- Google API Key (for Gemini models)

### 1. Clone the Repository

```bash
git clone https://github.com/AmgothSunil/BiteMate.git
cd BiteMate
```

### 2. Set Up Virtual Environment

Using `uv` (recommended):
```bash
uv venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

Or using standard Python:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

### 3. Install Dependencies

```bash
uv pip install -e .
# or
pip install -e .
```

### 4. Environment Configuration

Create a `.env` file in the project root by copying the example file:

```bash
cp .env.example .env
```

Then edit `.env` and fill in your actual values:

```env
# Google AI (Required)
GOOGLE_API_KEY=your_google_api_key_here

# PostgreSQL (Required)
PG_DB_NAME=bitemate_db
PG_USER=your_postgres_username
PG_PASSWORD=your_postgres_password
PG_HOST=localhost
PG_PORT=5432

# Pinecone (Required)
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_MEMORY_INDEX_NAME=bitemate-memory

# Optional: External APIs for enhanced features
NUTRITIONIX_APP_ID=your_nutritionix_app_id
NUTRITIONIX_API_KEY=your_nutritionix_api_key
SPOONACULAR_API_KEY=your_spoonacular_api_key
USDA_API_KEY=your_usda_api_key
```

**Where to get API keys:**
- **Google API Key**: [Google AI Studio](https://makersuite.google.com/app/apikey)
- **Pinecone**: [Pinecone.io](https://www.pinecone.io/)
- **Nutritionix**: [Developer Portal](https://developer.nutritionix.com/)
- **Spoonacular**: [Food API](https://spoonacular.com/food-api)
- **USDA**: [FoodData Central](https://fdc.nal.usda.gov/api-key-signup.html)


### 5. Database Setup

**PostgreSQL**:
```bash
# Create database
createdb bitemate_db

# Run migrations (if you have migration scripts)
# python -m alembic upgrade head
```

**Pinecone**:
- Create an index in Pinecone dashboard with dimension matching your embedding model (e.g., 384 for `all-MiniLM-L6-v2`)

---

## 💻 Usage

### Running the Application

#### 1. Start the FastAPI Backend

```bash
# Option 1: Using uvicorn directly
uvicorn src.bitemate.api.api:app --reload --host 0.0.0.0 --port 8000

# Option 2: Using the main script
python -m src.bitemate.api.api

# Option 3: Using uv
uv run uvicorn src.bitemate.api.api:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

#### 2. Start the Streamlit Frontend

In a new terminal:

```bash
streamlit run frontend/app.py
```

The UI will open at `http://localhost:8501`

### Using the API Directly

**Health Check**:
```bash
curl http://localhost:8000/api/health
```

**Generate Meal Plan**:
```bash
curl -X POST http://localhost:8000/api/meal-plan \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "session_id": "session_456",
    "user_input": "I want a healthy low-carb lunch"
  }'
```

### Example Prompts

**With Profile Information**:
```
I'm a 35-year-old male, 68kg, 175cm tall. I have pre-diabetes 
and I'm trying to eat low carb. I want a spicy lunch.
```

**Simple Request**:
```
I want healthy dinner recipes for 2 people
```

**Recipe Request**:
```
Show me the recipe for Chickpea Curry
```

---

## 📚 API Documentation

### Endpoints

#### `GET /`
Root endpoint with API information.

**Response**:
```json
{
  "message": "BiteMate API",
  "version": "1.0.0",
  "endpoints": {
    "health": "/api/health",
    "meal_plan": "/api/meal-plan (POST)"
  }
}
```

#### `GET /api/health`
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "service": "BiteMate API",
  "orchestrator": "initialized"
}
```

#### `POST /api/meal-plan`
Generate personalized meal plan.

**Request Body**:
```json
{
  "user_id": "string (required)",
  "session_id": "string (optional)",
  "user_input": "string (required)"
}
```

**Response**:
```json
{
  "user_id": "string",
  "session_id": "string",
  "response": "string (meal plan and instructions)",
  "status": "success"
}
```

**Error Response**:
```json
{
  "status_code": 500,
  "detail": "Error message"
}
```

---

## 🧪 Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test Files

```bash
pytest tests/test_orchestrator.py
pytest tests/test_meal_generator.py
pytest tests/test_router_agent.py
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Coverage

```bash
pytest --cov=src --cov-report=html
```

### Test Structure

```
tests/
├── test_orchestrator.py      # Orchestrator logic tests
├── test_meal_generator.py    # Meal generator pipeline tests
└── test_router_agent.py      # Router agent tests
```

---

## 📁 Project Structure

```
BiteMate/
├── frontend/
│   └── app.py                 # Streamlit UI
├── src/
│   └── bitemate/
│       ├── agents/
│       │   ├── meal_generator.py    # Meal planning agents
│       │   ├── orchestrator.py      # Master orchestrator
│       │   └── router_agent.py       # Intent classifier
│       ├── api/
│       │   └── api.py                # FastAPI application
│       ├── config/
│       │   └── params.yaml           # Configuration parameters
│       ├── core/
│       │   ├── exception.py          # Custom exceptions
│       │   └── logger.py             # Logging setup
│       ├── db/
│       │   ├── pinecone_memory_db.py # Vector database
│       │   └── postgre_db.py          # PostgreSQL operations
│       ├── prompts/
│       │   ├── generate_meal_prompt.txt
│       │   ├── user_profile_prompt.txt
│       │   └── orchestrator_prompt.txt
│       ├── tools/
│       │   ├── bitemate_tools.py     # Custom MCP tools
│       │   └── mcp_client.py         # MCP integration
│       └── utils/
│           ├── params.py              # Config loader
│           ├── prompt.py              # Prompt manager
│           └── run_sessions.py        # Agent session runner
├── tests/                     # Test suite
├── .env.example               # Example environment configuration
├── .gitignore
├── LICENSE
├── pyproject.toml             # Project metadata & dependencies
├── pytest.ini                 # Pytest configuration
├── README.md
└── requirements.txt
```

---

## 🔧 Development

### Code Quality

**Format code**:
```bash
black src/ tests/
isort src/ tests/
```

**Lint code**:
```bash
ruff check src/ tests/
mypy src/
```

**Pre-commit hooks** (optional):
```bash
pre-commit install
pre-commit run --all-files
```

### Adding New Features

1. **Create a new agent**: Add to `src/bitemate/agents/`
2. **Add new tools**: Extend `src/bitemate/tools/bitemate_tools.py`
3. **Update prompts**: Modify files in `src/bitemate/prompts/`
4. **Add tests**: Create corresponding test file in `tests/`

---

## 🌐 Deployment

### Production Considerations

1. **Environment Variables**: Use secrets manager (AWS Secrets Manager, Google Cloud Secret Manager)
2. **Database**: Set up production PostgreSQL with connection pooling
3. **Vector DB**: Configure Pinecone for production workloads
4. **API**: Deploy FastAPI with Gunicorn + Uvicorn workers
5. **Frontend**: Deploy Streamlit on Streamlit Cloud or containerize

### Docker Deployment (Coming Soon)

```bash
docker-compose up
```

---

## 📝 Configuration

### Model Configuration

Edit `src/bitemate/config/params.yaml`:

```yaml
meal_planner_agent:
  model_name: "gemini-2.0-flash"
  file_path: "meal_planner_agent.log"

router_agent:
  model_name: "gemini-2.0-flash"
  file_path: "router_agent.log"

orchestrator_agent:
  model_name: "gemini-2.0-flash"
  file_path: "orchestrator_agent.log"

retry_config_params:
  attempts: 5
  exp_base: 7
  initial_delay: 1
  http_status_codes: [429, 500, 503, 504]
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Contribution Guidelines

- Follow PEP 8 style guide
- Add tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting PR

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👥 Authors

- **Amgoth Sunil** - *Initial work* - [GitHub](https://github.com/AmgothSunil)

---

## 🙏 Acknowledgments

- Google ADK team for the Agentic Development Kit
- Google Gemini for powerful language models
- FastAPI and Streamlit communities
- Open-source contributors

---

## 📞 Support

For support, email amgothsunil422@gmail.com or open an issue on GitHub.

---

## 🗺️ Roadmap

- [ ] Docker containerization
- [ ] CI/CD pipeline setup
- [ ] Enhanced nutritional analysis
- [ ] Mobile app (React Native)
- [ ] Multi-language support
- [ ] Recipe image generation
- [ ] Social sharing features
- [ ] Meal prep planning
- [ ] Grocery list generation
- [ ] Integration with fitness trackers

---

<div align="center">

**Made with ❤️ using Google ADK and Gemini 2.0**

⭐ Star this repo if you find it helpful!

</div>
