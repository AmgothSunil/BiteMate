"""
Simple test script to verify agent pipeline creation and configuration.
Run with: uv run python -m tests.test_agent_pipelines
"""
from dotenv import load_dotenv
load_dotenv()

from src.bitemate.agents.user_profiler_agent import UserProfilingPipeline
from src.bitemate.agents.meal_planner_agent import MealPlannerPipeline


def test_user_profiler_pipeline():
    """Test User Profiler pipeline agent creation."""
    print("\n" + "="*70)
    print("TESTING USER PROFILER PIPELINE")
    print("="*70)
    
    try:
        pipeline = UserProfilingPipeline()
        agent_chain = pipeline.create_sequential_agent()
        
        print(f"\n✅ Agent Chain: {agent_chain.name}")
        print(f"✅ Sub-agents: {[agent.name for agent in agent_chain.sub_agents]}")
        print(f"✅ Output keys:")
        for agent in agent_chain.sub_agents:
            print(f"   - {agent.name}: {agent.output_key}")
        
        return True
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


def test_meal_planner_pipeline():
    """Test Meal Planner pipeline agent creation."""
    print("\n" + "="*70)
    print("TESTING MEAL PLANNER PIPELINE")
    print("="*70)
    
    try:
        pipeline = MealPlannerPipeline()
        agent_chain = pipeline.create_sequential_agent()
        
        print(f"\n✅ Agent Chain: {agent_chain.name}")
        print(f"✅ Sub-agents: {[agent.name for agent in agent_chain.sub_agents]}")
        print(f"✅ Output keys:")
        for agent in agent_chain.sub_agents:
            print(f"   - {agent.name}: {agent.output_key}")
        
        return True
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("BITEMATE AGENT PIPELINE TESTS")
    print("="*70)
    
    user_profiler_ok = test_user_profiler_pipeline()
    meal_planner_ok = test_meal_planner_pipeline()
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print(f"User Profiler: {'✅ PASSED' if user_profiler_ok else '❌ FAILED'}")
    print(f"Meal Planner: {'✅ PASSED' if meal_planner_ok else '❌ FAILED'}")
    print("="*70)
    
    if user_profiler_ok and meal_planner_ok:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️  SOME TESTS FAILED")
