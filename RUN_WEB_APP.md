# Running BiteMate Web Application

## Prerequisites

Make sure you have all dependencies installed:

```bash
# Install additional dependencies for web app
uv pip install fastapi uvicorn streamlit requests
```

## Running the Application

You need to run **two separate terminals**:

### Terminal 1: FastAPI Backend

```bash
# Navigate to project directory
cd "D:\Google Capstone\BiteMate"

# Run FastAPI server
uv run python api.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Keep this terminal running!**

### Terminal 2: Streamlit Frontend

```bash
# Navigate to project directory
cd "D:\Google Capstone\BiteMate"

# Run Streamlit app
uv run streamlit run app.py
```

Your browser will automatically open to `http://localhost:8501`

**Keep this terminal running too!**

## Using the Application

1. **Open Browser**: Go to `http://localhost:8501`

2. **Enter Your Request**: 
   ```
   Example: I'm a 30-year-old male, 75kg, 180cm tall. 
   I have type 2 diabetes and I'm vegetarian. 
   I want healthy dinner recipes.
   ```

3. **Click "Generate Meal Plan"**

4. **View Results**: 
   - Profile status (created/updated)
   - 5+ meal recipe options
   - Saved in PostgreSQL automatically

## Testing API Directly

You can also test the API directly:

```bash
curl -X POST http://localhost:8000/api/meal-plan \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "user_input": "I want healthy lunch recipes",
    "num_meals": 5
  }'
```

## Troubleshooting

### "Cannot connect to API"
- Make sure FastAPI is running on port 8000
- Check Terminal 1 for any errors
- Run: `curl http://localhost:8000/api/health`

### "Request timed out"
- Normal for first request (models loading)
- Increased timeout to 120 seconds
- Check Terminal 1 for logs

### Port already in use
```bash
# Kill process on port 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Kill process on port 8501
netstat -ano | findstr :8501
taskkill /PID <PID> /F
```

## Architecture

```
User Browser (Streamlit)
    ↓ HTTP Request
FastAPI Backend (:8000)
    ↓
BiteMateOrchestrator
    ↓
[User Profiler Pipeline] + [Meal Planner Pipeline]
    ↓
PostgreSQL (save) + Pinecone (profile)
    ↓
Response → User Browser
```

## Features

### Streamlit Frontend
- ✅ Beautiful UI with custom CSS
- ✅ Example inputs for quick testing
- ✅ History tracking
- ✅ Adjustable number of meals
- ✅ Profile update notifications

### FastAPI Backend
- ✅ RESTful API
- ✅ CORS enabled
- ✅ Proper error handling
- ✅ Health check endpoint
- ✅ Async support

### Integration
- ✅ Auto-saves to PostgreSQL
- ✅ Profile detection
- ✅ Meal plan generation
- ✅ Complete conversation history

Enjoy your AI-powered meal planning! 🍽️
