"""Client for the Travel Agent.

Discovers the Travel Agent, sends queries, and prints responses.
Demonstrates the A2A client flow: discover -> connect -> communicate.

Run: python client.py
     python client.py --demo    (scripted demo)
(Requires travel_agent.py on port 5002, and currency_agent.py on port 5001)
"""

import asyncio
import sys
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import (
    Message,
    Role,
    TaskState,
    TextPart,
)


async def discover_agent(base_url: str):
    """Discover an agent by fetching its agent card."""
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=base_url,
        )
        return await resolver.get_agent_card()


def extract_text(parts) -> str:
    """Extract text from a list of parts."""
    for part in parts:
        if hasattr(part, "root"):
            part = part.root
        if isinstance(part, TextPart):
            return part.text
    return ""


async def send_and_print(client, text: str) -> None:
    """Send a message and print the response."""
    message = Message(
        role=Role.user,
        parts=[TextPart(text=text)],
        messageId=uuid4().hex,
    )
    response = client.send_message(message)

    async for chunk in response:
        task, _ = chunk

        if task.status.state == TaskState.completed:
            for artifact in task.artifacts:
                text = extract_text(artifact.parts)
                if text:
                    print(f"  {text}")
        elif task.status.state == TaskState.failed:
            if task.status.message:
                err = extract_text(task.status.message.parts)
                print(f"  Error: {err}")
            else:
                print(f"  Task failed")
        else:
            print(f"  Task state: {task.status.state}")


async def interactive(base_url: str) -> None:
    """Run an interactive session with the agent."""
    print(f"Discovering agent at {base_url}...")
    card = await discover_agent(base_url)
    print(f"Connected to: {card.name}")
    print(f"Description:  {card.description}")
    if card.skills:
        print(f"Skills:       {', '.join(s.name for s in card.skills)}")
    print()

    factory = ClientFactory(config=ClientConfig(streaming=False))
    client = factory.create(card)

    print("Type a query (or 'quit' to exit). Try:")
    print("  list")
    print("  flight to paris")
    print("  hotel in tokyo in USD")
    print("  dinner in london in EUR")
    print()

    try:
        while True:
            try:
                text = input("> ").strip()
            except EOFError:
                break
            if not text or text.lower() in ("quit", "exit", "q"):
                break

            await send_and_print(client, text)
            print()
    finally:
        await client.close()


async def demo(base_url: str) -> None:
    """Run a scripted demo showing agent-to-agent communication."""
    print(f"Discovering agent at {base_url}...")
    card = await discover_agent(base_url)
    print(f"Connected to: {card.name}")
    print(f"Description:  {card.description}")
    print()

    factory = ClientFactory(config=ClientConfig(streaming=False))
    client = factory.create(card)

    queries = [
        "list",
        "flight to paris",
        "flight to paris in USD",
        "hotel in tokyo in USD",
        "dinner in london in EUR",
        "boat on lake zurich in JPY",
    ]

    try:
        for query in queries:
            print(f"> {query}")
            await send_and_print(client, query)
            print()
    finally:
        await client.close()


if __name__ == "__main__":
    base_url = "http://localhost:5002"

    if "--demo" in sys.argv:
        asyncio.run(demo(base_url))
    else:
        asyncio.run(interactive(base_url))
