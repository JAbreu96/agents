from src.agent import Agent


def test_agent_think_returns_response():
    agent = Agent(name="TestAgent")
    response = agent.think("foo")
    assert response == "TestAgent received: foo"
