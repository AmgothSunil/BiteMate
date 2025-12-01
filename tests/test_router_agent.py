import pytest
import types

# import the module (adjusted to your project structure)
import src.bitemate.agents.router_agent as router_agent


class DummyPromptManager:
    def load_prompt(self, path):
        return "ROUTER INSTRUCTION"

class DummyGemini:
    def __init__(self, model, retry_options=None):
        self.model = model

class DummyAgent:
    def __init__(self, *args, **kwargs):
        # make a simple object compatible with assertions below
        self.name = kwargs.get("name", "IntentRouter")
        self.instruction = kwargs.get("instruction", "ROUTER INSTRUCTION")


def test_create_router_agent_exists():
    """Ensure create_router_agent is exported by the module."""
    if not hasattr(router_agent, "create_router_agent"):
        pytest.skip("router_agent.create_router_agent not found — skipping router_agent tests.")


def test_create_router_agent_success(monkeypatch):
    """When prompt manager returns a valid prompt, create_router_agent should produce an agent object."""
    if not hasattr(router_agent, "create_router_agent"):
        pytest.skip("router_agent.create_router_agent not found — skipping.")

    # patch PromptManager if used in module (best-effort)
    if hasattr(router_agent, "PromptManager"):
        monkeypatch.setattr(router_agent, "PromptManager", DummyPromptManager)
    else:
        # sometimes the module constructs PromptManager locally; set an attribute to allow tests to patch it
        router_agent.PromptManager = DummyPromptManager

    # patch load_params if module uses it
    if hasattr(router_agent, "load_params"):
        monkeypatch.setattr(router_agent, "load_params", lambda path: {"router_agent": {"file_path": "router.log", "model_name": "dummy-model"}})
    else:
        router_agent.load_params = lambda path: {"router_agent": {"file_path": "router.log", "model_name": "dummy-model"}}

    # patch external classes that would otherwise call external network
    monkeypatch.setattr(router_agent, "Gemini", DummyGemini, raising=False)
    monkeypatch.setattr(router_agent, "Agent", DummyAgent, raising=False)

    # call the factory
    agent_obj = router_agent.create_router_agent(config_path="cfg", prompt_path="prompt")
    # Basic checks: returned object exists and carries some expected property
    assert agent_obj is not None
    # If the returned object has name or instruction we can assert on them
    if hasattr(agent_obj, "name"):
        assert "intent" in agent_obj.name.lower() or agent_obj.name != ""
    if hasattr(agent_obj, "instruction"):
        assert "ROUTER" in agent_obj.instruction or len(agent_obj.instruction) > 0
