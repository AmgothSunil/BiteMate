import pytest
import inspect

# import module (your layout)
import src.bitemate.agents.orchestrator as orchestrator_module


def test_orchestrator_export_exists():
    if not hasattr(orchestrator_module, "BiteMateOrchestrator"):
        pytest.skip("BiteMateOrchestrator not present; skipping tests.")


def test_get_execution_agent_choices_and_fallback(monkeypatch):
    """Ensure _get_execution_agent returns valid objects for UPDATE_PROFILE, GENERATE_PLAN, FULL_FLOW and fallback."""

    OrchCls = orchestrator_module.BiteMateOrchestrator
    sig = inspect.signature(OrchCls)

    # --- Patch SequentialAgent to avoid pydantic validation during the test ---
    class DummySequentialAgent:
        def __init__(self, name: str, description: str, sub_agents: list):
            self.name = name
            self.description = description
            self.sub_agents = sub_agents

    # Replace directly inside the orchestrator module
    monkeypatch.setattr(orchestrator_module, "SequentialAgent", DummySequentialAgent, raising=False)

    # Also inject a dummy Agent type if needed anywhere (optional)
    class DummyAgentObj:
        def __init__(self, name="dummy"):
            self.name = name

    # Minimal DummyPipeline that returns proper agent-like objects (not raw strings)
    class DummyPipeline:
        def create_profiler_agent(self):
            return DummyAgentObj("profiler")
        def create_meal_generator_agent(self):
            return DummyAgentObj("planner")

    # Build kwargs for the orchestrator ctor using its signature (best-effort)
    kwargs = {}
    for pname in sig.parameters:
        kwargs[pname] = None

    # Override args we need
    kwargs.update({
        "config_path": "src/bitemate/config/params.yaml",
        "meal_planner_pipeline": DummyPipeline(),
        "session_service": None,
        "memory_service": None,
        "model_name": "dummy",
        "retry_options": None,
        "allowed_router_outputs": ["UPDATE_PROFILE", "GENERATE_PLAN", "FULL_FLOW"]
    })

    orch = OrchCls(**{k: v for k, v in kwargs.items() if k in sig.parameters})

    # Test known choices
    a = orch._get_execution_agent("UPDATE_PROFILE")
    assert a is not None

    a2 = orch._get_execution_agent("GENERATE_PLAN")
    assert a2 is not None

    # FULL_FLOW should now produce our DummySequentialAgent without pydantic validation errors
    full = orch._get_execution_agent("FULL_FLOW")
    assert isinstance(full, DummySequentialAgent)
    assert hasattr(full, "sub_agents") and len(full.sub_agents) == 2

    # Unknown decision should fallback (should not raise)
    fallback = orch._get_execution_agent("SOMETHING_UNKNOWN")
    assert fallback is not None
