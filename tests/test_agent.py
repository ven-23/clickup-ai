import pytest
from agent import app
from langchain_core.messages import HumanMessage

def test_agent_initialization():
    """Verify that the agent app compiles correctly."""
    assert app is not None

def test_agent_graph_structure():
    """Verify the nodes in the graph."""
    # This is a bit internal but verifies the setup
    assert "generator" in app.nodes
    assert "executor" in app.nodes
    assert "formatter" in app.nodes

@pytest.mark.skip(reason="Requires live database and OpenAI API key")
def test_agent_invocation():
    """Verify a simple invocation (requires env vars)."""
    input_state = {"messages": [HumanMessage(content="Hello")]}
    result = app.invoke(input_state)
    assert "messages" in result
    assert len(result["messages"]) > 0
