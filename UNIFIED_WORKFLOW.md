# Unified Workflow - Single Input System

## What Changed

The orchestrator now has a **unified workflow** that takes a SINGLE user input and intelligently handles everything.

---

## How It Works Now

### **New Method: `execute_unified_workflow()`**

```python
orchestrator = BiteMateOrchestrator()

# ONE input handles everything!
result = await orchestrator.execute_unified_workflow(
    user_id="user123",
    user_input="I want healthy lunch recipes",  # Single input!
    num_meals=5  # Number of meal options
)
```

### **Intelligent Processing**

The orchestrator automatically:

1. **Detects Profile Info**: Scans input for keywords like "I'm", "years old", "diabetic", "vegetarian", etc.
2. **Creates/Updates Profile**: If profile info detected → runs user profiling pipeline
3. **Generates Meals**: Always runs meal planning pipeline with enhanced request for multiple options
4. **Returns Results**: Profile status + meal options

---

## Examples

### Example 1: Simple Request (No Profile Info)

```python
user_input = "I want healthy lunch recipes"

result = await orchestrator.execute_unified_workflow(
    user_id="user123",
    user_input=user_input,
    num_meals=5
)
```

**What Happens**:
```
1. No profile keywords detected
2. Skip profile creation
3. Generate 5 meal options
4. Return meal options
```

**Result**:
```python
{
    "user_id": "user123",
    "profile_updated": False,
    "profile_response": None,
    "meal_options": [5 different meal recipes],
    "num_meals_requested": 5,
    "status": "success"
}
```

### Example 2: Request WITH Profile Info

```python
user_input = """
I'm a 30-year-old male, 75kg, 180cm tall. 
I have type 2 diabetes and I'm vegetarian. 
I want healthy dinner recipes.
"""

result = await orchestrator.execute_unified_workflow(
    user_id="user123",
    user_input=user_input,
    num_meals=5
)
```

**What Happens**:
```
1. Profile keywords detected ("I'm", "years old", "kg", "diabetic", "vegetarian")
2. Run user profiling pipeline:
   - Extract bio-data
   - Calculate nutrition needs
   - Save to database
3. Generate 5 meal options (using saved profile)
4. Return both profile confirmation + meals
```

**Result**:
```python
{
    "user_id": "user123",
    "profile_updated": True,  # Profile was created!
    "profile_response": ["✅ Profile Created Successfully..."],
    "meal_options": [5 diabetes-friendly vegetarian recipes],
    "num_meals_requested": 5,
    "status": "success"
}
```

---

## Key Features

### 1. **Smart Profile Detection**

Keywords monitored:
- Personal info: `"i'm"`, `"i am"`, `"years old"`, `"kg"`, `"cm"`, `"tall"`, `"weight"`
- Health: `"diabetic"`, `"diabetes"`, `"allergy"`, `"allergic"`  
- Diet: `"vegetarian"`, `"vegan"`
- Preferences: `"prefer"`, `"don't like"`, `"hate"`, `"love"`

### 2. **Enhanced Meal Request**

Input is automatically enhanced:
```python
original_input = "I want lunch recipes"

# Becomes:
enhanced_input = """
I want lunch recipes

IMPORTANT: Please provide at least 5 different meal options with:
- Recipe names
- Ingredients
- Nutritional information
- Cooking instructions

Ensure variety in protein sources, cooking methods, and flavors.
"""
```

### 3. **Error Resilience**

If profile creation fails, workflow continues:
```python
try:
    profile_response = await self.execute_user_profiling(...)
    profile_updated = True
except Exception as e:
    self.logger.warning(f"Profile update failed, continuing: {e}")
    # Still generates meals!
```

---

## Usage Patterns

### Pattern 1: Quick Meal Request

```python
# User just wants meals, no profile setup
await orchestrator.execute_unified_workflow(
    user_id="quick_user",
    user_input="Give me 5 pasta recipes",
    num_meals=5
)
```

### Pattern 2: First-Time User

```python
# User provides profile + meal request in one go
await orchestrator.execute_unified_workflow(
    user_id="new_user",
    user_input="I'm 25F, vegan, need breakfast ideas",
    num_meals=5
)
```

### Pattern 3: Returning User

```python
# User already has profile, just requests meals
await orchestrator.execute_unified_workflow(
    user_id="returning_user",  # Profile exists in DB
    user_input="I want dinner for today",
    num_meals=5
)
```

---

## Under the Hood

### Workflow Diagram

```
User Input: "I'm diabetic, want lunch recipes"
    ↓
┌─────────────────────────────────────────┐
│  execute_unified_workflow()             │
├─────────────────────────────────────────┤
│                                         │
│  Step 1: Scan for profile keywords     │
│  └─→ Found: "diabetic" ✅              │
│                                         │
│  Step 2: Run User Profiling Pipeline   │
│  ├─→ UserProfiler: Extract data        │
│  ├─→ NutritionCalculator: Calculate    │
│  └─→ ProfileUpdater: Save to DB        │
│                                         │
│  Step 3: Enhance meal request          │
│  └─→ Add "provide at least 5 options"  │
│                                         │
│  Step 4: Run Meal Planning Pipeline    │
│  ├─→ RecipeFinder: Find recipes        │
│  ├─→ DailyMealPlanner: Create plan     │
│  ├─→ MealGenerator: Cook instructions  │
│  └─→ VarietyAgent: Check variety       │
│                                         │
│  Step 5: Return results                │
│  └─→ {profile_updated, meal_options}   │
└─────────────────────────────────────────┘
```

---

## Testing

Run the unified workflow examples:

```bash
uv run python -m src.bitemate.agents.orchestrator
```

This runs:
1. **Example 1**: Simple meal request (no profile)
2. **Example 2**: Request with profile info
3. **Example 3**: Complete workflow (old method for comparison)

---

## API Integration

### FastAPI Example

```python
from fastapi import FastAPI
from src.bitemate.agents.orchestrator import BiteMateOrchestrator

app = FastAPI()
orchestrator = BiteMateOrchestrator()

@app.post("/api/meal-request")
async def handle_meal_request(user_id: str, message: str, num_meals: int = 5):
    """Single endpoint handles everything!"""
    result = await orchestrator.execute_unified_workflow(
        user_id=user_id,
        user_input=message,
        num_meals=num_meals
    )
    return result

# Usage:
# POST /api/meal-request
# {
#   "user_id": "user123",
#   "message": "I'm diabetic, want lunch ideas",
#   "num_meals": 5
# }
```

---

## Benefits

### ✅ **Simpler for Users**
- One input, everything handled
- Don't need to know about profile vs meals
- Natural conversation flow

### ✅ **Intelligent Processing**
- Automatically detects profile needs
- Updates profile when info provided
- Uses existing profile when available

### ✅ **Flexible**
- Works for new users (creates profile)
- Works for returning users (uses profile)
- Works for quick queries (skips profile)

### ✅ **Scalable**
- Easy to adjust `num_meals` parameter
- Can customize profile detection keywords
- Can enhance meal request format

---

## Summary

**Before**: User had to explicitly call user profiling, then meal planning  
**Now**: User provides ONE input, system intelligently handles everything

Single method does it all: `execute_unified_workflow()` 🎉
