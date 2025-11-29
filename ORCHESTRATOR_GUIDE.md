# BiteMate Orchestrator - How It Works

## Overview

The **Orchestrator** is the central controller that manages both the User Profiler and Meal Planner pipelines. It coordinates the entire workflow from user input to final response.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BiteMateOrchestrator                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────┐       ┌──────────────────────┐    │
│  │ Shared Services     │       │ Pipeline Management  │    │
│  ├─────────────────────┤       ├──────────────────────┤    │
│  │ • SessionService    │       │ • UserProfilingPipe  │    │
│  │ • MemoryService     │───────│ • MealPlannerPipe    │    │
│  │ • SessionManager    │       │ • Runners (lazy)     │    │
│  └─────────────────────┘       └──────────────────────┘    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Execution Methods                         │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │ • execute_user_profiling()                           │  │
│  │ • execute_meal_planning()                             │  │
│  │ • execute_complete_workflow()                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## How I Built It

### 1. **Class Structure**

```python
class BiteMateOrchestrator:
    """Main orchestrator class"""
    
    def __init__(self, config_path):
        # Initialize shared services (SAME instances for both pipelines)
        self.session_service = InMemorySessionService()
        self.memory_service = InMemoryMemoryService()
        self.session_manager = SessionManager()
        
        # Initialize both pipelines
        self.user_profiler_pipeline = UserProfilingPipeline()
        self.meal_planner_pipeline = MealPlannerPipeline()
        
        # Runners created lazily (when first needed)
        self._user_profiler_runner = None
        self._meal_planner_runner = None
```

**Key Design Decision**: Shared services ensure both pipelines access the same session/memory state.

### 2. **Runner Management (Lazy Initialization)**

```python
def _get_user_profiler_runner(self) -> Runner:
    """Create runner only when needed (lazy loading)"""
    if self._user_profiler_runner is None:
        agent_chain = self.user_profiler_pipeline.create_sequential_agent()
        self._user_profiler_runner = Runner(
            app_name="agents",
            agent=agent_chain,
            session_service=self.session_service,  # Shared
            memory_service=self.memory_service      # Shared
        )
    return self._user_profiler_runner
```

**Why Lazy?** Agents are only initialized when first used, saving resources.

### 3. **Three Execution Modes**

#### **Mode 1: User Profiling Only**

```python
async def execute_user_profiling(user_id, user_input):
    """
    Creates/updates user profile
    Workflow: Extract → Calculate → Save
    """
    runner = self._get_user_profiler_runner()
    
    context_variables = {
        "user_id": user_id,
        "user_input": user_input
    }
    
    responses = await self.session_manager.run_session(
        runner_instance=runner,
        user_queries=user_input,
        session_id=f"{user_id}_profile",
        context_variables=context_variables
    )
    
    return responses
```

**Flow**:
```
User Input
    ↓
UserProfiler → extracts bio-data → saved to Pinecone
    ↓
NutritionCalculator → calculates BMR/TDEE/macros
    ↓
ProfileUpdater → saves goals → confirmation
```

#### **Mode 2: Meal Planning Only**

```python
async def execute_meal_planning(user_id, user_input):
    """
    Plans meals for existing user
    Workflow: Recall → Find → Plan → Cook → Check
    """
    runner = self._get_meal_planner_runner()
    
    context_variables = {
        "user_id": user_id,
        "user_input": user_input,
        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    responses = await self.session_manager.run_session(
        runner_instance=runner,
        user_queries=user_input,
        session_id=f"{user_id}_meal_{date}",
        context_variables=context_variables
    )
    
    return responses
```

**Flow**:
```
Meal Request
    ↓
RecipeFinder → recalls profile → finds recipes
    ↓
DailyMealPlanner → creates B/L/D plan → saves
    ↓
MealGenerator → generates cooking instructions
    ↓
VarietyAgent → checks variety → final response
```

#### **Mode 3: Complete Workflow**

```python
async def execute_complete_workflow(user_id, profile_input, meal_input):
    """
    For new users: Create profile THEN plan meals
    """
    # Step 1: Profile
    profile_responses = await self.execute_user_profiling(
        user_id=user_id,
        user_input=profile_input
    )
    
    # Step 2: Meal Plan (uses profile from Step 1)
    meal_responses = await self.execute_meal_planning(
        user_id=user_id,
        user_input=meal_input
    )
    
    return {
        "profile_response": profile_responses,
        "meal_plan_response": meal_responses,
        "status": "success"
    }
```

**Flow**:
```
Complete Workflow Request
    ↓
Step 1: User Profiling
    UserProfiler → NutritionCalculator → ProfileUpdater
    ↓
Step 2: Meal Planning (using saved profile)
    RecipeFinder → DailyMealPlanner → MealGenerator → VarietyAgent
    ↓
Both responses returned
```

---

## Key Features

### 1. **Shared Services**
- Same `session_service` and `memory_service` for both pipelines
- Ensures data consistency across workflows
- Session state persists between pipeline executions

### 2. **Context Variables**
- Passed to agents via template substitution
- Available in prompts as `{user_id}`, `{user_input}`, etc.
- Automatically injected into session state

### 3. **Session Management**
- User profiling: `{user_id}_profile`
- Meal planning: `{user_id}_meal_{date}`
- Allows tracking separate workflows per user

### 4. **Error Handling**
- Try-catch blocks with detailed logging
- AppException for consistent error reporting
- Logger tracks entire execution flow

### 5. **Async Execution**
- All methods are `async` for better performance
- Can be easily integrated into async web frameworks
- Non-blocking execution

---

## Usage Examples

### Example 1: Create User Profile

```python
orchestrator = BiteMateOrchestrator()

profile_input = """
I'm a 30-year-old male, 75kg, 180cm tall.
I have type 2 diabetes and prefer vegetarian Indian food.
I want to lose weight.
"""

responses = await orchestrator.execute_user_profiling(
    user_id="user123",
    user_input=profile_input
)

print(responses)
```

**Output**: Confirmation that profile is created with calculated nutrition goals.

### Example 2: Plan Meals

```python
meal_request = "I need a healthy lunch plan for today."

responses = await orchestrator.execute_meal_planning(
    user_id="user123",
    user_input=meal_request
)

print(responses)
```

**Output**: Complete meal plan with recipes and cooking instructions.

### Example 3: Complete Workflow (New User)

```python
result = await orchestrator.execute_complete_workflow(
    user_id="new_user",
    profile_input="I'm 25F, 60kg, 165cm, vegan...",
    meal_input="Create a high-protein meal plan"
)

print(result['profile_response'])
print(result['meal_plan_response'])
```

**Output**: Both profile confirmation and meal plan.

---

## Testing the Orchestrator

### Run the Examples

```bash
# This will run all three examples automatically
uv run python -m src.bitemate.agents.orchestrator
```

### Integration with API/Frontend

```python
from fastapi import FastAPI
from src.bitemate.agents.orchestrator import BiteMateOrchestrator

app = FastAPI()
orchestrator = BiteMateOrchestrator()

@app.post("/api/profile")
async def create_profile(user_id: str, profile_data: str):
    response = await orchestrator.execute_user_profiling(user_id, profile_data)
    return {"response": response}

@app.post("/api/meal-plan")
async def plan_meals(user_id: str, meal_request: str):
    response = await orchestrator.execute_meal_planning(user_id, meal_request)
    return {"response": response}
```

---

## Why This Design?

### ✅ **Separation of Concerns**
- Pipelines define WHAT agents do
- Orchestrator defines WHEN and HOW to execute

### ✅ **Reusability**
- Can execute either pipeline independently
- Or combine them in sequence
- Easy to add new workflows

### ✅ **Maintainability**
- Changes to agent logic in pipeline files
- Changes to execution flow in orchestrator
- Clear boundaries

### ✅ **Scalability**
- Easy to add more pipelines (e.g., Shopping List Generator)
- Shared services ensure efficient resource usage
- Can be deployed independently

---

## What Happens Under the Hood

### When you call `execute_meal_planning()`:

1. **Orchestrator** gets the meal planner runner
2. **Runner** creates a session with ID `user123_meal_20251129`
3. **Context variables** `{user_id}`, `{user_input}`, `{current_time}` are added to session state
4. **Sequential agent** starts executing:
   - RecipeFinder uses `recall_user_profile(user_id='user123')` tool → gets profile from Pinecone
   - RecipeFinder uses `search_recipes()` tool → finds recipes
   - RecipeFinder outputs to `found_recipes` key
   - DailyMealPlanner receives `{found_recipes}` from previous agent
   - DailyMealPlanner creates meal plan → outputs to `daily_meal_plan` key
   - MealGenerator receives `{daily_meal_plan}` → generates instructions
   - VarietyAgent receives `{cooking_instructions}` → provides final output
5. **Session manager** collects all responses and returns them

---

## Files Updated/Created

1. ✅ **`src/bitemate/agents/orchestrator.py`** - Main orchestrator class
2. ✅ **`ORCHESTRATOR_GUIDE.md`** - This documentation
3. ✅ **Updated** `task.md` with orchestrator tasks

---

## Next Steps

1. **Test with real data**: Run the orchestrator examples
2. **Build API**: Create FastAPI endpoints using orchestrator
3. **Add frontend**: Connect UI to orchestrator API
4. **Deploy**: Package and deploy the complete system

The orchestrator is now ready to coordinate your entire BiteMate AI system! 🎉
