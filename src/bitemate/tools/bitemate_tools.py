import os
import sys
import requests
import json
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Third-party imports
from mcp.server.fastmcp import FastMCP
from langchain_community.tools import ArxivQueryRun, WikipediaQueryRun
from langchain_community.utilities import ArxivAPIWrapper, WikipediaAPIWrapper

# Internal imports (Your refactored modules)
from src.bitemate.db.pinecone_memory_db import UserProfileMemory
from src.bitemate.db.postgre_db import PostgresManager
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

# 1. Initialization & Configuration
load_dotenv()
logger = setup_logger("BiteMateTools", "mcp_tools.log")

# API Keys
NUTRITIONIX_APP_ID = os.getenv("NUTRITIONIX_APP_ID")
NUTRITIONIX_API_KEY = os.getenv("NUTRITIONIX_API_KEY")
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")
USDA_API_KEY = os.getenv("USDA_API_KEY") # Added for USDA

# Initialize Services (Fail Gracefully)
try:
    logger.info("Initializing Database Services...")
    pinecone_memory = UserProfileMemory()
    postgre_memory = PostgresManager()
    
    # Initialize LangChain Wrappers
    arxiv = ArxivQueryRun(api_wrapper=ArxivAPIWrapper())
    wikipedia = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())
    
    logger.info("Services initialized successfully.")
except Exception as e:
    logger.critical(f"Service initialization failed: {e}")
    sys.exit(1)

# Initialize MCP Server
mcp = FastMCP(
    "BiteMateTools", 
    dependencies=["requests", "psycopg2-binary", "pinecone", "langchain"]
)

# --------------------------------------------------------------------------
# 🧠 MEMORY TOOLS (Database Interactions)
# --------------------------------------------------------------------------

@mcp.tool()
def save_user_preference(user_id: str, preference_text: str,  medical_info: str, category: str = "general") -> str:
    """
    Saves a user's core preference (e.g., 'I am vegan', 'I hate mushrooms') into long-term memory.
    
    Args:
        user_id (str): The ID of the user.
        preference_text (str): The detail to remember.
        category (str): Category (e.g., 'allergy', 'diet', 'appliance').
    """
    try:
        mem_id = pinecone_memory.add_user_preference(user_id, preference_text, category, medical_info)
        return f"Success: Preference saved with ID {mem_id}"
    except Exception as e:
        logger.error(f"Error saving preference: {e}")
        return f"Error: Could not save preference. {str(e)}"

# @mcp.tool()
# def recall_user_profile(user_id: str, context_query: str) -> str:
#     """
#     Retrieves relevant user preferences based on the current context.
#     Use this before generating recipes to check for allergies or dislikes.
    
#     Args:
#         user_id (str): The user ID.
#         context_query (str): What is happening (e.g., 'planning dinner with chicken').
#     """
#     try:
#         results = pinecone_memory.get_relevant_profile(user_id, context_query)
#         if not results:
#             return "No relevant past preferences found."
        
#         # Format as a clean string for the LLM
#         memories = [f"- [{m['category']}] {m['text']}" for m in results]
#         return "User Profile Context:\n" + "\n".join(memories)
#     except Exception as e:
#         return f"Error retrieving profile: {str(e)}"

@mcp.tool()
def get_recent_conversation(user_id: str, session_id: str, limit: int = 5) -> str:
    """
    Fetches the last few messages from the chat history to understand context.
    """
    try:
        history = postgre_memory.get_session_history(user_id, session_id, limit)
        return postgre_memory.format_history_for_llm(history)
    except Exception as e:
        return f"Error fetching history: {str(e)}"

@mcp.tool()
def save_generated_meal_plan(user_id: str, session_id: str, plan_summary: str, recipes_json: dict):
    """
    Saves a completed meal plan to PostgreSQL for permanent storage.
    Use this when the user accepts a meal plan.
    
    Args:
        user_id (str): User ID.
        session_id (str): Session ID.
        plan_summary (str): Text summary (e.g., "Week 1 Diabetic Indian Plan").
        recipes_json (dict): The structured recipe data.
    """
    try:
        # We reuse the add_message function, but in a real app, 
        # you might have a specific 'meal_plans' table.
        # Here we store it as a system log with metadata.
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
    CRITICAL: Call this FIRST. Retrieves dietary restrictions and CUISINE preferences.
    
    Args:
        context (str): e.g., "planning dinner".
    """
    try:
        results = pinecone_memory.get_relevant_profile(user_id, context)
        if not results:
            return "No specific preferences found (assume general diet)."
        
        # We format this clearly so the Agent sees "Cuisine: Indian"
        output = ["User Profile / Preferences:"]
        for m in results:
            output.append(f"- [{m['category']}] {m['text']}")
        return "\n".join(output)
    except Exception as e:
        return f"Error: {e}"


# --------------------------------------------------------------------------
# 🥦 EXTERNAL API TOOLS (Nutrition & Recipes)
# --------------------------------------------------------------------------

@mcp.tool()
def search_nutrition_info(query: str) -> str:
    """
    Fetch calories, protein, and macros for a specific food item using Nutritionix.
    
    Args:
        query (str): Food name (e.g., "1 cup cooked rice", "2 large eggs").
    """
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
        
        # Data Cleaning: Extract only what matters to save tokens
        foods = []
        for item in data.get("foods", []):
            foods.append(f"{item['food_name']} ({item['serving_weight_grams']}g): "
                         f"{item['nf_calories']} kcal, "
                         f"Protein: {item['nf_protein']}g, "
                         f"Carbs: {item['nf_total_carbohydrate']}g, "
                         f"Fat: {item['nf_total_fat']}g")
        
        return "\n".join(foods) if foods else "No nutritional info found."

    except requests.exceptions.RequestException as e:
        logger.error(f"Nutritionix API Error: {e}")
        return f"Error connecting to nutrition database: {e}"

@mcp.tool()
def search_recipes(query: str, diet: Optional[str] = None) -> str:
    """
    Search for recipes using Spoonacular API.
    
    Args:
        query (str): Recipe keyword (e.g., 'pasta', 'chicken curry').
        diet (str, optional): Diet filter (e.g., 'vegetarian', 'vegan', 'gluten free').
    """
    params = {
        "apiKey": SPOONACULAR_API_KEY,
        "query": query,
        "addRecipeInformation": True,
        "addRecipeNutrition": True,
        "number": 3  # Limit to 3 to save context window
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

        # Simplify output
        simplified = []
        for r in results:
            info = (f"Title: {r['title']}\n"
                    f"Time: {r['readyInMinutes']} mins\n"
                    f"Calories: {r.get('nutrition', {}).get('nutrients', [{}])[0].get('amount', 'N/A')} kcal\n"
                    f"Link: {r.get('sourceUrl', 'N/A')}")
            simplified.append(info)
            
        return "\n---\n".join(simplified)

    except requests.exceptions.RequestException as e:
        return f"Error fetching recipes: {str(e)}"

@mcp.tool()
def search_usda_database(query: str) -> str:
    """
    Search for generic food items in the USDA FoodData Central database.
    Useful for raw ingredients (e.g., 'raw spinach', 'flour').
    """
    if not USDA_API_KEY:
        return "Error: USDA_API_KEY not configured."

    try:
        response = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"query": query, "pageSize": 3, "api_key": USDA_API_KEY},
            timeout=10
        )
        # FIX: Check status_code properly
        if response.status_code == 200:
            data = response.json()
            foods = data.get("foods", [])
            output = []
            for f in foods:
                desc = f.get("description", "Unknown")
                # Try to find protein/energy in foodNutrients
                output.append(f"- {desc}")
            return "\n".join(output) if output else "No USDA data found."
        else:
            return f"USDA API Error: {response.status_code} - {response.text}"
            
    except Exception as e:
        return f"Error connecting to USDA: {e}"

# --------------------------------------------------------------------------
# 📚 RESEARCH TOOLS
# --------------------------------------------------------------------------

@mcp.tool()
def search_scientific_papers(query: str) -> str:
    """Searches Arxiv for scientific papers. Useful for checking health claims."""
    try:
        return arxiv.run(query)
    except Exception as e:
        return f"Arxiv Error: {e}"

@mcp.tool()
def search_wikipedia(query: str) -> str:
    """Searches Wikipedia for general food knowledge or cultural dishes."""
    try:
        return wikipedia.run(query)
    except Exception as e:
        return f"Wikipedia Error: {e}"


if __name__ == "__main__":
    # Standard: Allow port configuration via Env or CLI
    port = int(os.getenv("MCP_PORT", 8000))
    mcp.run(transport="streamable-http") 
    # Note: 'transport' arg depends on specific FastMCP version, 
    # usually it defaults to stdio or sse. Adjust based on your specific library version.

