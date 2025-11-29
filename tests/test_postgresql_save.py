"""
Test script to verify save_generated_meal_plan works correctly.
This bypasses the agent and calls the tool directly.
"""
import sys
sys.path.insert(0, '.')
from src.bitemate.tools.bitemate_tools import save_generated_meal_plan

def test_direct_save():
    """Test saving directly to PostgreSQL."""
    print("\n" + "="*70)
    print("TESTING DIRECT SAVE TO POSTGRESQL")
    print("="*70)
    
    # Test data
    test_user_id = "test_user_direct"
    test_session_id = "test_session_direct"
    test_summary = "Test Recipe Options - Direct Save"
    test_recipes = {
        "recipes": [
            {
                "name": "Test Recipe 1",
                "description": "A test recipe",
                "ingredients": ["ingredient1", "ingredient2"],
                "nutrition": {"calories": 350, "protein": 35},
                "time": "25 minutes"
            },
            {
                "name": "Test Recipe 2",
                "description": "Another test recipe",
                "ingredients": ["ingredient3", "ingredient4"],
                "nutrition": {"calories": 400, "protein": 40},
                "time": "30 minutes"
            }
        ]
    }
    
    try:
        # Call the save function directly
        print(f"\nAttempting to save meal plan...")
        print(f"User ID: {test_user_id}")
        print(f"Session ID: {test_session_id}")
        print(f"Summary: {test_summary}")
        
        result = save_generated_meal_plan(
            user_id=test_user_id,
            session_id=test_session_id,
            plan_summary=test_summary,
            recipes_json=test_recipes
        )
        
        print(f"\n✅ RESULT: {result}")
        print("\n" + "="*70)
        print("SUCCESS! Check your PostgreSQL database:")
        print("="*70)
        print("\nRun this SQL query in pgAdmin4:")
        print("```sql")
        print("SELECT * FROM chat_history")
        print(f"WHERE user_id = '{test_user_id}'")
        print(f"AND session_id = '{test_session_id}';")
        print("```")
        print("\nYou should see 1 row with:")
        print(f"  - content: 'MEAL_PLAN_SAVED: {test_summary}'")
        print(f"  - metadata: [JSON with test recipes]")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_direct_save()
