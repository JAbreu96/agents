"""Minimal AI agent scaffold."""

import time


class Agent:
    def __init__(self, name: str = "SimpleAgent"):
        self.name = name

    def think(self, prompt: str) -> str:
        """Return a simple transformed response."""
        time.sleep(0.1)
        return f"{self.name} received: {prompt}"


def main() -> None:
    agent = Agent()
    prompt = "Hello, agent!"
    print("Prompt:", prompt)
    print("Response:", agent.think(prompt))


if __name__ == "__main__":
    main()
