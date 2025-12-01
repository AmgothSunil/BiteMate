import pytest
import inspect

# import module
import src.bitemate.agents.meal_generator as meal_module


def test_module_exports_present():
    """Check basic exports: MealPlannerPipeline should exist."""
    assert hasattr(meal_module, "MealPlannerPipeline"), "MealPlannerPipeline not found in meal_generator module"


def test_meal_generator_basic_instantiation(monkeypatch):
    """Test that MealPlannerPipeline can be instantiated with mocked dependencies."""
    
    # Mock the load_params to return a valid config without needing the actual file
    def mock_load_params(path):
        return {
            "meal_planner_agent": {
                "model_name": "gemini-1.5-flash"
            }
        }
    
    # Mock PromptManager to avoid loading actual prompt files
    class MockPromptManager:
        def load_prompt(self, path):
            return "Mock prompt content"
    
    # Apply mocks
    monkeypatch.setattr(meal_module, "load_params", mock_load_params)
    monkeypatch.setattr(meal_module, "PromptManager", MockPromptManager)
    
    # Mock environment variable for API key validation
    monkeypatch.setenv("GOOGLE_API_KEY", "mock_api_key")
    
    # Instantiate MealPlannerPipeline with minimal args
    pipeline = meal_module.MealPlannerPipeline(
        config_path="src/bitemate/config/params.yaml"
    )
    
    assert pipeline is not None
    assert hasattr(pipeline, "create_profiler_agent")
    assert hasattr(pipeline, "create_meal_generator_agent")
