# tests/test_meal_planner_pipeline.py
import pytest
from types import SimpleNamespace
from src.bitemate.agents.consolidated_meal_generator import MealPlannerPipeline, RetryConfigSpec

class DummyPromptManager:
    def load_prompt(self, path):
        return "dummy prompt"

class DummyToolset:
    pass

def test_pipeline_initialization_with_injected_deps(tmp_path, monkeypatch):
    # Set required env var
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-tests")

    # Create a minimal fake params.yaml on disk and point config path.
    cfg = tmp_path / "params.yaml"
    cfg.write_text("meal_planner_agent:\n  model_name: 'gemini-1.5-flash'\n")

    pipeline = MealPlannerPipeline(
        config_path=str(cfg),
        prompt_manager=DummyPromptManager(),
        toolset=DummyToolset(),
        retry_spec=RetryConfigSpec(attempts=1)
    )

    profiler = pipeline.create_profiler_agent()
    meal_agent = pipeline.create_meal_generator_agent()

    assert profiler.name == "UnifiedProfileManager"
    assert meal_agent.name == "UnifiedMealChef"
