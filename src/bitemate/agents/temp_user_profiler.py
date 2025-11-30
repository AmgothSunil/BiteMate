# Insert / replace into src/bitemate/agents/temp_user_profiler.py
import sys
import os
import asyncio
import threading
import inspect
from typing import Optional, List, Any, Callable
from dotenv import load_dotenv

# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents import Agent, SequentialAgent
from google.adk.models.google_llm import Gemini

# --- Internal Core Imports ---
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException
from src.bitemate.utils.prompt import PromptManager

# --- Tool Imports (local fallbacks) ---
from src.bitemate.tools.bitemate_tools import (
    save_user_preference,
    recall_user_profile,
    search_nutrition_info,
    search_usda_database,
    search_scientific_papers
)

# MultiServer MCP Client
from langchain_mcp_adapters.client import MultiServerMCPClient

# Load Environment Variables
load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# Constants
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

# Prompt Manager
prompt_manager = PromptManager()

# Retry Configuration
RETRY_CONFIG = types.HttpRetryOptions(
    initial_delay=1,
    attempts=5,
    max_delay=60,
    exp_base=2,
    jitter=0.2,
    http_status_codes=[429, 500, 503, 504]
)

# ------------------------
# Helper: run coroutine in separate thread (safe when main loop exists)
# ------------------------
def _run_coro_in_thread(coro):
    """Run coroutine in a new event loop inside a background thread and return result."""
    result = {"value": None, "exc": None}

    def _runner():
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro)
        except Exception as e:
            result["exc"] = e
        finally:
            if loop is not None:
                try:
                    loop.close()
                except Exception:
                    pass

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if result["exc"]:
        raise result["exc"]
    return result["value"]

# ------------------------
# get remote tools synchronously (unchanged)
# ------------------------
def get_tools_sync(client_config: Optional[dict] = None) -> List[Any]:
    if client_config is None:
        client_config = {
            "bitemate": {
                "url": "http://localhost:8000/mcp",
                "transport": "streamable_http"
            }
        }

    try:
        client = MultiServerMCPClient(client_config)
        tools = _run_coro_in_thread(client.get_tools())
        if isinstance(tools, list):
            return tools
        try:
            return list(tools)
        except Exception:
            print(f"[get_tools_sync] Unexpected type from client.get_tools(): {type(tools)}")
            return []
    except Exception as e:
        print(f"[get_tools_sync] Error fetching tools from MultiServerMCPClient: {e}")
        return []

# ------------------------
# Adapt remote StructuredTool -> callable wrapper
# ------------------------
def adapt_remote_tools(remote_tools: List[Any], timeout_seconds: float = 30.0) -> List[Callable]:
    """
    Convert the remote StructuredTool objects into callables expected by the Agent.
    The returned callable accepts a single argument (payload/dict or string) and returns the tool's result.
    """
    adapted = []

    def _is_async_callable(fn):
        return inspect.iscoroutinefunction(fn) or inspect.isawaitable(fn)

    def _select_executor_attr(tool):
        """
        Heuristic to find an executable on the StructuredTool object.
        Returns (callable_obj, attr_name) or (None, None).
        """
        # 1. if object itself is callable
        if callable(tool):
            return tool, "__call__"

        # 2. common method names
        for attr in ("call", "invoke", "run", "execute", "start"):
            if hasattr(tool, attr) and callable(getattr(tool, attr)):
                return getattr(tool, attr), attr

        # 3. sometimes there is a 'callable' attribute (callable holder)
        if hasattr(tool, "callable"):
            candidate = getattr(tool, "callable")
            if callable(candidate):
                return candidate, "callable"

        # 4. some tool containers expose `.tool` or `.fn`
        for attr in ("tool", "fn", "func"):
            if hasattr(tool, attr) and callable(getattr(tool, attr)):
                return getattr(tool, attr), attr

        return None, None

    for t in remote_tools:
        try:
            executor, attr_name = _select_executor_attr(t)
            if executor is None:
                # Skip tools we can't execute, but log them
                print(f"[adapt_remote_tools] Warning: could not detect executable on tool: {getattr(t,'name',repr(t))}")
                continue

            # define wrapper
            def make_wrapper(executor, tool_obj):
                # Bind name/desc for introspection
                tool_name = getattr(tool_obj, "name", getattr(tool_obj, "id", None)) or f"remote_tool_{id(tool_obj)}"
                tool_desc = getattr(tool_obj, "description", getattr(tool_obj, "desc", ""))

                # If executor is a coroutine function or returns a coroutine, run it safely
                async_flag = inspect.iscoroutinefunction(executor)

                def wrapper(payload):
                    """
                    payload: typically a dict or str; we pass-through to remote tool
                    """
                    try:
                        # If executor itself expects (payload, **kwargs) or just payload; we pass as single arg
                        result = executor(payload)
                        # If result is awaitable (coroutine), run it in thread loop so caller remains sync
                        if inspect.isawaitable(result):
                            return _run_coro_in_thread(result)
                        return result
                    except TypeError:
                        # maybe the executor expects no args; try calling without payload
                        try:
                            result = executor()
                            if inspect.isawaitable(result):
                                return _run_coro_in_thread(result)
                            return result
                        except Exception as ex2:
                            raise ex2
                    except Exception as ex:
                        # re-raise with context
                        raise RuntimeError(f"Remote tool '{tool_name}' execution error: {ex}") from ex

                # set metadata attributes many frameworks look for
                try:
                    wrapper.__name__ = f"remote_{tool_name}"
                except Exception:
                    pass
                wrapper.__doc__ = f"Remote tool wrapper for {tool_name}: {tool_desc}"
                # Attach friendly attrs
                setattr(wrapper, "name", tool_name)
                setattr(wrapper, "description", tool_desc)
                # Optionally attach original remote object for debugging
                setattr(wrapper, "_remote_tool_obj", tool_obj)
                return wrapper

            adapted_tool = make_wrapper(executor, t)
            adapted.append(adapted_tool)

        except Exception as e:
            print(f"[adapt_remote_tools] Error adapting tool {getattr(t,'name',repr(t))}: {e}")
            continue

    return adapted

# ------------------------
# UserProfilingPipeline (uses adapted callables)
# ------------------------
class UserProfilingPipeline:
    def __init__(self, config_path: str = CONFIG_REL_PATH):
        try:
            # Load Configuration
            self.params = load_params(config_path)
            self.agent_config = self.params.get("user_profiler_agent", {})

            # Setup Logger
            log_file = self.agent_config.get("file_path", "user_profiling.log")
            self.logger = setup_logger(name="UserProfilingPipeline", log_file_name=log_file)

            # Model Configuration
            self.model_name = self.agent_config.get("model_name", "gemini-2.5-flash")

            # Initialize remote tools and adapt into callables (cache once)
            try:
                ms_config = self.agent_config.get("multiserver_config", None)
                raw_tools = get_tools_sync(ms_config)
                adapted = adapt_remote_tools(raw_tools)
                if not adapted:
                    self.logger.warning("No adapted remote tools available; falling back to local tool callables.")
                    # create wrappers around local functions (already callables)
                    adapted = [save_user_preference, recall_user_profile,
                               search_nutrition_info, search_usda_database, search_scientific_papers]
                self._tools = adapted
                self.logger.info(f"Using {len(self._tools)} tools for agents.")
            except Exception as e:
                self.logger.error(f"Failed to fetch/ adapt remote tools: {e}")
                self._tools = [save_user_preference, recall_user_profile,
                               search_nutrition_info, search_usda_database, search_scientific_papers]

            self.logger.info("UserProfilingPipeline initialized successfully.")
        except Exception as e:
            msg = f"Failed to initialize UserProfilingPipeline: {str(e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)

    def _create_profiler_agent(self) -> Agent:
        instruction = prompt_manager.load_prompt(
            "src/bitemate/prompts/user_profiler_prompts/create_profiler_prompt.txt"
        )
        return Agent(
            name="UserProfiler",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Extracts bio-data and saves it to the vector database.",
            instruction=instruction,
            tools=self._tools,
            output_key="extracted_profile_json"
        )

    def _create_calculator_agent(self) -> Agent:
        instruction = prompt_manager.load_prompt(
            "src/bitemate/prompts/user_profiler_prompts/create_calculator_prompt.txt"
        )
        return Agent(
            name="NutritionCalculator",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Calculates nutritional needs based on extracted profile.",
            instruction=instruction,
            tools=self._tools,
            output_key="calculated_macros"
        )

    def _create_updater_agent(self) -> Agent:
        instruction = prompt_manager.load_prompt(
            "src/bitemate/prompts/user_profiler_prompts/create_updater_prompt.txt"
        )
        return Agent(
            name="ProfileUpdater",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Saves the final calculated goals back to memory.",
            instruction=instruction,
            tools=self._tools
        )

    def create_sequential_agent(self) -> SequentialAgent:
        try:
            self.logger.info("Building User Profiling Sequential Agent Chain...")
            profiler = self._create_profiler_agent()
            calculator = self._create_calculator_agent()
            updater = self._create_updater_agent()
            root_agent = SequentialAgent(
                name="UserProfilingChain",
                sub_agents=[profiler, calculator, updater]
            )
            self.logger.info("User Profiling Sequential Agent Chain created successfully.")
            return root_agent
        except Exception as e:
            self.logger.error(f"Error creating sequential agent: {e}")
            raise AppException(f"Agent Creation Failed: {e}", sys)

# ---------------- Example usage ----------------
if __name__ == "__main__":
    try:
        pipeline = UserProfilingPipeline()
        pipeline = UserProfilingPipeline()
        print("Tool names:", [getattr(t, "name", None) for t in pipeline._tools])

        agent_chain = pipeline.create_sequential_agent()
        print(f"✅ User Profiling Agent Chain Created: {agent_chain.name}")
        print(f"   Sub-agents: {[agent.name for agent in agent_chain.sub_agents]}")
    except Exception as err:
        print(f"\n❌ SETUP FAILED: {err}")
