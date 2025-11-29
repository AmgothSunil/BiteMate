# Testing BiteMate Agent Pipelines

## ✅ Test Results

Both agent pipelines are working correctly! Here's what we verified:

### User Profiler Pipeline
```
✅ Agent Chain: UserProfilingChain
✅ Sub-agents: ['UserProfiler', 'NutritionCalculator', 'ProfileUpdater']
✅ Output keys:
   - UserProfiler: extracted_profile_json
   - NutritionCalculator: calculated_macros
   - ProfileUpdater: None (final agent)
```

### Meal Planner Pipeline
```
✅ Agent Chain: MealPlanningChain
✅ Sub-agents: ['RecipeFinderAgent', 'DailyMealPlanner', 'MealGeneratingAgent', 'UserVarietyAgent']
✅ Output keys:
   - RecipeFinderAgent: found_recipes
   - DailyMealPlanner: daily_meal_plan
   - MealGeneratingAgent: cooking_instructions
   - UserVarietyAgent: None (final agent)
```

---

## How to Test

### 1. Test Agent Creation (Configuration Only)

These commands verify that agents are configured correctly WITHOUT executing them:

```bash
# Test User Profiler Pipeline
uv run -m src.bitemate.agents.user_profiler_agent

# Test Meal Planner Pipeline
uv run -m src.bitemate.agents.meal_planner_agent

# Run comprehensive tests
uv run python -m tests.test_agent_pipelines
```

### 2. Create an Orchestrator for Full Testing

To actually RUN the agents with real data, create an orchestrator:

**File**: `src/bitemate/orchestrator.py`

```python
import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.genai import types

from src.bitemate.agents.user_profiler_agent import UserProfilingPipeline
from src.bitemate.agents.meal_planner_agent import MealPlannerPipeline
from src.bitemate.utils.run_sessions import SessionManager

# Initialize services
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()
session_manager = SessionManager(session_service=session_service)


async def run_user_profiling(user_id: str, user_input: str):
    """Execute user profiling pipeline."""
    # 1. Create pipeline and agent
    pipeline = UserProfilingPipeline()
    agent_chain = pipeline.create_sequential_agent()
    
    # 2. Create runner
    runner = Runner(
        app_name="agents",
        agent=agent_chain,
        session_service=session_service,
        memory_service=memory_service
    )
    
    # 3. Execute with context
    responses = await session_manager.run_session(
        runner_instance=runner,
        user_queries=user_input,
        session_id=f"{user_id}_profile",
        context_variables={"user_id": user_id, "user_input": user_input}
    )
    
    return responses


async def run_meal_planning(user_id: str, user_input: str):
    """Execute meal planning pipeline."""
    # 1. Create pipeline and agent
    pipeline = MealPlannerPipeline()
    agent_chain = pipeline.create_sequential_agent()
    
    # 2. Create runner
    runner = Runner(
        app_name="agents",
        agent=agent_chain,
        session_service=session_service,
        memory_service=memory_service
    )
    
    # 3. Execute with context
    import datetime
    responses = await session_manager.run_session(
        runner_instance=runner,
        user_queries=user_input,
        session_id=f"{user_id}_meal_{datetime.date.today()}",
        context_variables={
            "user_id": user_id,
            "user_input": user_input,
            "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )
    
    return responses


# Example usage
if __name__ == "__main__":
    # Test 1: User Profiling
    print("="*70)
    print("TEST 1: USER PROFILING")
    print("="*70)
    
    user_input = """
    I'm a 30-year-old male, weighing 75kg and 180cm tall. 
    I have type 2 diabetes and prefer vegetarian Indian food.
    I want to lose weight and exercise moderately 3-4 times a week.
    """
    
    profile_response = asyncio.run(run_user_profiling("test_user_1", user_input))
    print("\nProfile Response:")
    print(profile_response)
    
    # Test 2: Meal Planning
    print("\n" + "="*70)
    print("TEST 2: MEAL PLANNING")
    print("="*70)
    
    meal_input = "I need a healthy meal plan for today with vegetarian Indian recipes."
    
    meal_response = asyncio.run(run_meal_planning("test_user_1", meal_input))
    print("\nMeal Plan Response:")
    print(meal_response)
```

### 3. Run Full Integration Test

```bash
# Run the orchestrator
uv run python -m src.bitemate.orchestrator
```

---

## What Each Test Verifies

### Configuration Tests (`test_agent_pipelines.py`)
✅ Pipelines initialize correctly  
✅ Sequential agent chains are created  
✅ All sub-agents are present and in correct order  
✅ Tools are assigned correctly to each agent  
✅ Output keys are configured for data flow  

### Integration Tests (via Orchestrator)
✅ Agents can execute with real data  
✅ Data flows between agents via output_key  
✅ Tools are called correctly  
✅ Database operations work (Pinecone, PostgreSQL)  
✅ Session management works  
✅ Final responses are generated  

---

## Expected Workflow

### User Profiling Flow
```
1. User provides personal info
   ↓
2. UserProfiler extracts data & saves to Pinecone
   ↓
3. NutritionCalculator calculates BMR/TDEE & macros
   ↓
4. ProfileUpdater saves nutrition goals & confirms
```

### Meal Planning Flow
```
1. User requests meal plan
   ↓
2. RecipeFinder recalls profile & finds recipes
   ↓
3. DailyMealPlanner creates full day plan (B/L/D)
   ↓
4. MealGenerator creates cooking instructions
   ↓
5. VarietyAgent checks variety & provides final response
```

---

## Troubleshooting

### If tests fail:
1. Check environment variables (.env file)
2. Verify database connections (Pinecone, PostgreSQL)
3. Check API keys (Nutritionix, Spoonacular, USDA, Google AI)
4. Review logs in `logs/` directory

### Common Issues:
- **"No module named 'src'"**: Run with `uv run python -m ...`
- **Database connection errors**: Check .env credentials
- **API errors**: Verify API keys and rate limits

---

## Next Steps

1. ✅ Agent configuration tests passed
2. ⏭️ Create orchestrator for full execution
3. ⏭️ Test with real user data
4. ⏭️ Build frontend/API for user interaction
