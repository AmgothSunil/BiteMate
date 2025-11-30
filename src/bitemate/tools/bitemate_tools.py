"""
BiteMate MCP Server - Fixed version with proper session handling
Reference: FastMCP documentation
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
try:
    from src.bitemate.db.pinecone_memory_db import UserProfileMemory
    from src.bitemate.db.postgre_db import PostgresManager
except ImportError:
    print("⚠️  Database modules not available - tools will operate in read-only mode")
    UserProfileMemory = None
    PostgresManager = None

from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

# ============================================================================
# 1. Initialization & Configuration
# ============================================================================

load_dotenv()
logger = setup_logger("BiteMateTools", "mcp_tools.log")

# API Keys
NUTRITIONIX_APP_ID = os.getenv("NUTRITIONIX_APP_ID")
NUTRITIONIX_API_KEY = os.getenv("NUTRITIONIX_API_KEY")
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")
USDA_API_KEY = os.getenv("USDA_API_KEY")

# Initialize Services (Fail Gracefully)
pinecone_memory = None
postgre_memory = None

try:
    logger.info("Initializing Database Services...")
    if UserProfileMemory:
        pinecone_memory = UserProfileMemory()
    if PostgresManager:
        postgre_memory = PostgresManager()

    logger.info("Services initialized successfully.")
except Exception as e:
    logger.warning(f"Service initialization with warning: {e}")
    logger.info("Continuing with available services only...")

# ============================================================================
# Initialize FastMCP Server - Corrected per documentation
# ============================================================================

mcp = FastMCP(
    "BiteMateTools",
    dependencies=["requests", "psycopg2-binary", "pinecone", "langchain"]
)

logger.info(f"FastMCP server initialized: {mcp.name}")

# ============================================================================
# 🧠 MEMORY TOOLS (Database Interactions)
# ============================================================================

@mcp.tool()
def save_user_preference(user_id: str, preference_text: str, medical_info: str, category: str = "general") -> str:
    """
    Saves a user's core preference into long-term memory.
    
    Args:
        user_id (str): The ID of the user.
        preference_text (str): The detail to remember.
        medical_info (str): Medical context.
        category (str): Category (e.g., 'allergy', 'diet', 'appliance').
    """
    try:
        if not pinecone_memory:
            return "Warning: Pinecone not initialized. Preference not saved."
        
        mem_id = pinecone_memory.add_user_preference(user_id, preference_text, category, medical_info)
        return f"Success: Preference saved with ID {mem_id}"
    except Exception as e:
        logger.error(f"Error saving preference: {e}")
        return f"Error: Could not save preference. {str(e)}"


@mcp.tool()
def get_recent_conversation(user_id: str, session_id: str, limit: int = 5) -> str:
    """
    Fetches the last few messages from chat history to understand context.
    """
    try:
        if not postgre_memory:
            return "Warning: PostgreSQL not initialized. No history available."
        
        history = postgre_memory.get_session_history(user_id, session_id, limit)
        return postgre_memory.format_history_for_llm(history)
    except Exception as e:
        return f"Error fetching history: {str(e)}"


@mcp.tool()
def save_information_to_postgre(user_id: str, session_id: str, plan_summary: str, recipes_json: dict) -> str:
    """
    Saves a completed meal plan to PostgreSQL for permanent storage.
    """
    try:
        if not postgre_memory:
            return "Warning: PostgreSQL not initialized. Plan not saved."
        
        postgre_memory.add_message(
            user_id=user_id,
            session_id=session_id,
            role="system",
            content=f"MEAL_PLAN_SAVED: {plan_summary}",
            metadata=recipes_json
        )
        return "Meal plan saved to database successfully."
    except Exception as e:
        logger.error(f"Postgres Save Error: {e}")
        return f"Error saving meal plan: {e}"


@mcp.tool()
def recall_user_profile(user_id: str, context: str) -> str:
    """
    Retrieves dietary restrictions and CUISINE preferences.
    
    Args:
        user_id (str): User ID
        context (str): e.g., "planning dinner"
    """
    try:
        if not pinecone_memory:
            return "No specific preferences found (Pinecone not initialized)."
        
        results = pinecone_memory.get_relevant_profile(user_id, context)
        if not results:
            return "No specific preferences found (assume general diet)."
        
        output = ["User Profile / Preferences:"]
        for m in results:
            output.append(f"- [{m['category']}] {m['text']}")
        return "\n".join(output)
    except Exception as e:
        return f"Error: {e}"

# ============================================================================
# 🥦 EXTERNAL API TOOLS (Nutrition & Recipes)
# ============================================================================

@mcp.tool()
def search_nutrition_info(query: str) -> str:
    """
    Fetch calories, protein, and macros using Nutritionix API.
    
    Args:
        query (str): Food name (e.g., "1 cup cooked rice", "2 large eggs")
    """
    if not NUTRITIONIX_APP_ID or not NUTRITIONIX_API_KEY:
        return "Error: Nutritionix API credentials not configured."
    
    headers = {
        "x-app-id": NUTRITIONIX_APP_ID,
        "x-app-key": NUTRITIONIX_API_KEY,
        "Content-Type": "application/json",
    }
    
    try:
        resp = requests.post(
            "https://trackapi.nutritionix.com/v2/natural/nutrients",
            headers=headers,
            json={"query": query},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        
        foods = []
        for item in data.get("foods", []):
            foods.append(
                f"{item['food_name']} ({item['serving_weight_grams']}g): "
                f"{item['nf_calories']} kcal, "
                f"Protein: {item['nf_protein']}g, "
                f"Carbs: {item['nf_total_carbohydrate']}g, "
                f"Fat: {item['nf_total_fat']}g"
            )
        
        return "\n".join(foods) if foods else "No nutritional info found."
    except requests.exceptions.RequestException as e:
        logger.error(f"Nutritionix API Error: {e}")
        return f"Error connecting to nutrition database: {e}"


@mcp.tool()
def search_recipes(query: str, diet: Optional[str] = None) -> str:
    """
    Search for recipes using Spoonacular API.
    
    Args:
        query (str): Recipe keyword (e.g., 'pasta', 'chicken curry')
        diet (str, optional): Diet filter (e.g., 'vegetarian', 'vegan')
    """
    if not SPOONACULAR_API_KEY:
        return "Error: Spoonacular API key not configured."
    
    params = {
        "apiKey": SPOONACULAR_API_KEY,
        "query": query,
        "addRecipeInformation": True,
        "addRecipeNutrition": True,
        "number": 3
    }
    
    if diet:
        params["diet"] = diet
    
    try:
        response = requests.get(
            "https://api.spoonacular.com/recipes/complexSearch",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        
        if not results:
            return "No recipes found."
        
        simplified = []
        for r in results:
            info = (
                f"Title: {r['title']}\n"
                f"Time: {r['readyInMinutes']} mins\n"
                f"Link: {r.get('sourceUrl', 'N/A')}"
            )
            simplified.append(info)
        
        return "\n---\n".join(simplified)
    except requests.exceptions.RequestException as e:
        return f"Error fetching recipes: {str(e)}"


@mcp.tool()
def search_usda_database(query: str) -> str:
    """
    Search for generic food items in USDA FoodData Central database.
    """
    if not USDA_API_KEY:
        return "Error: USDA_API_KEY not configured."
    
    try:
        response = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"query": query, "pageSize": 3, "api_key": USDA_API_KEY},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            foods = data.get("foods", [])
            output = []
            for f in foods:
                desc = f.get("description", "Unknown")
                output.append(f"- {desc}")
            return "\n".join(output) if output else "No USDA data found."
        else:
            return f"USDA API Error: {response.status_code}"
    except Exception as e:
        return f"Error connecting to USDA: {e}"


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("BiteMate MCP Server Starting...")
    logger.info("=" * 70)
    
    try:
        # Start the MCP server
        # Google ADK automatically handles stdio/HTTP transport
        port = int(os.getenv("MCP_PORT", 8000))
        logger.info(f"MCP Server listening on port {port}")
        
        # FastMCP will use stdio by default when run as a module
        mcp.run()
        
    except KeyboardInterrupt:
        logger.info("MCP Server shutdown by user")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"MCP Server failed: {e}")
        sys.exit(1)
