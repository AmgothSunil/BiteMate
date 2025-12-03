"""
BiteMate MCP Server
"""

import os
import sys
import requests
import json
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Third-party imports
from mcp.server.fastmcp import FastMCP

# Internal imports
from src.bitemate.core.logger import setup_logger

# ============================================================================
# 1. Initialization & Configuration
# ============================================================================

load_dotenv()
logger = setup_logger("BiteMateTools", "mcp_tools.log")

# --- CRITICAL FIX: Write non-JSON logs to STDERR, never STDOUT ---
def log_safe(message: str):
    sys.stderr.write(f"[BiteMateTools] {message}\n")
    sys.stderr.flush()

# Import DBs safely
UserProfileMemory = None
PostgresManager = None

try:
    from src.bitemate.db.pinecone_memory_db import UserProfileMemory
    from src.bitemate.db.postgre_db import PostgresManager
except ImportError:
    log_safe("⚠️ Database modules not found. Running in stateless mode.")

# API Keys
NUTRITIONIX_APP_ID = os.getenv("NUTRITIONIX_APP_ID")
NUTRITIONIX_API_KEY = os.getenv("NUTRITIONIX_API_KEY")
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")
USDA_API_KEY = os.getenv("USDA_API_KEY")

# Initialize Services
pinecone_memory = None
postgre_memory = None

try:
    if UserProfileMemory:
        pinecone_memory = UserProfileMemory()
    if PostgresManager:
        postgre_memory = PostgresManager()
    log_safe("Database services initialized.")
except Exception as e:
    log_safe(f"Service initialization warning: {e}")

# ============================================================================
# Initialize FastMCP Server
# ============================================================================

mcp = FastMCP(
    "BiteMateTools",
    dependencies=["requests", "psycopg2-binary", "pinecone", "langchain"]
)

# ============================================================================
# 🧠 MEMORY TOOLS
# ============================================================================

@mcp.tool()
def save_user_preference(user_id: str, preference_text: str, medical_info: str = "", category: str = "general") -> str:
    """Saves user preference to Pinecone."""
    try:
        if not pinecone_memory:
            return "System Error: Memory database not active."
        mem_id = pinecone_memory.add_user_preference(user_id, preference_text, category, medical_info)
        return f"✅ SUCCESS: User preference saved successfully with ID: {mem_id}. Do not retry this operation."
    except Exception as e:
        logger.error(f"Error saving preference: {e}")
        return f"Error: {str(e)}"

@mcp.tool()
def get_recent_conversation(user_id: str, session_id: str, limit: int = 5) -> str:
    """Fetches chat history."""
    try:
        if not postgre_memory:
            return "No history available (DB inactive)."
        history = postgre_memory.get_session_history(user_id, session_id, limit)
        return postgre_memory.format_history_for_llm(history)
    except Exception as e:
        return f"Error fetching history: {str(e)}"

@mcp.tool()
def save_information_to_postgre(user_id: str, session_id: str, plan_summary: str, recipes_json: dict = {}) -> str:
    """Saves meal plan to Postgres."""
    try:
        if not postgre_memory:
            return "System Error: Database not active."
        postgre_memory.add_message(
            user_id=user_id, session_id=session_id, role="system",
            content=f"MEAL_PLAN_SAVED: {plan_summary}", metadata=recipes_json
        )
        return "✅ SUCCESS: Meal plan saved successfully to database. Do not retry this operation."
    except Exception as e:
        logger.error(f"Postgres Save Error: {e}")
        return f"Error saving plan: {e}"

@mcp.tool()
def recall_user_profile(user_id: str, context: str) -> str:
    """Retrieves relevant user profile data."""
    try:
        if not pinecone_memory:
            return "No profile data (DB inactive)."
        results = pinecone_memory.get_relevant_profile(user_id, context)
        if not results:
            return "No specific preferences found."
        
        output = ["User Profile:"]
        for m in results:
            output.append(f"- [{m.get('category','info')}] {m.get('text','')}")
        return "\n".join(output)
    except Exception as e:
        return f"Error recalling profile: {e}"

# ============================================================================
# 🥦 EXTERNAL API TOOLS
# ============================================================================

@mcp.tool()
def search_nutrition_info(query: str) -> str:
    """Fetch nutrition info via Nutritionix."""
    if not NUTRITIONIX_APP_ID: return "Configuration Error: Missing API Keys."
    
    try:
        resp = requests.post(
            "https://trackapi.nutritionix.com/v2/natural/nutrients",
            headers={
                "x-app-id": NUTRITIONIX_APP_ID,
                "x-app-key": NUTRITIONIX_API_KEY,
                "Content-Type": "application/json",
            },
            json={"query": query}, timeout=10
        )
        if resp.status_code != 200: return "No nutrition data found."
        data = resp.json()
        output = []
        for item in data.get("foods", []):
            output.append(f"{item['food_name']}: {item['nf_calories']}kcal, P:{item['nf_protein']}g")
        return "\n".join(output)
    except Exception as e:
        return f"API Error: {e}"

@mcp.tool()
def search_recipes(query: str, diet: Optional[str] = None) -> str:
    """Search recipes via Spoonacular."""
    if not SPOONACULAR_API_KEY: return "Configuration Error: Missing API Key."
    
    params = {"apiKey": SPOONACULAR_API_KEY, "query": query, "number": 3, "addRecipeNutrition": True}
    if diet: params["diet"] = diet
    
    try:
        resp = requests.get("https://api.spoonacular.com/recipes/complexSearch", params=params, timeout=10)
        data = resp.json()
        results = data.get("results", [])
        if not results: return "No recipes found."
        return "\n".join([f"{r['title']} (Ready in {r['readyInMinutes']}m)" for r in results])
    except Exception as e:
        return f"API Error: {e}"

@mcp.tool()
def search_usda_database(query: str) -> str:
    """Search USDA Food Database."""
    if not USDA_API_KEY: return "Configuration Error: Missing USDA Key."
    try:
        resp = requests.get("https://api.nal.usda.gov/fdc/v1/foods/search", 
                           params={"query": query, "pageSize": 3, "api_key": USDA_API_KEY}, timeout=10)
        data = resp.json()
        return "\n".join([f"- {f['description']}" for f in data.get("foods", [])])
    except Exception as e:
        return f"API Error: {e}"

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    # NO PRINT STATEMENTS HERE!
    try:
        mcp.run(transport="sse")
    except Exception as e:
        sys.exit(1)