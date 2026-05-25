from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState


DEFAULT_AGENT_URL = "http://localhost:5010"
DEFAULT_PROMPT = "Generate a gyroid surface"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Client for the Implicit Geometry A2A agent.")
    parser.add_argument("prompt", nargs="*", help="Surface prompt to send to the agent.")
    parser.add_argument("--url", default=DEFAULT_AGENT_URL, help="Agent base URL.")
    parser.add_argument("--out", default="outputs", help="Directory for returned GLB files.")
    args = parser.parse_args()

    prompt = " ".join(args.prompt).strip() or DEFAULT_PROMPT
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=args.url)
        card = await resolver.get_agent_card()

    print(f"Connected to: {card.name}")
    print(f"> {prompt}")

    factory = ClientFactory(config=ClientConfig(streaming=False))
    client = factory.create(card)

    try:
        message = Message(
            role=Role.ROLE_USER,
            parts=[Part(text=prompt)],
            message_id=uuid4().hex,
        )
        response = client.send_message(SendMessageRequest(message=message))

        async for stream_response in response:
            if not stream_response.HasField("task"):
                continue

            task = stream_response.task
            if task.status.state == TaskState.TASK_STATE_FAILED:
                text = _extract_status_text(task)
                print(f"Error: {text or 'task failed'}")
                return
            if task.status.state != TaskState.TASK_STATE_COMPLETED:
                continue

            for artifact in task.artifacts or []:
                for part in artifact.parts:
                    if part.text:
                        print(part.text)
                    elif part.raw:
                        file_name = part.filename or "surface.glb"
                        path = output_dir / file_name
                        path.write_bytes(part.raw)
                        print(f"Saved {path}")
    finally:
        await client.close()


def _extract_status_text(task) -> str:
    if not task.status.message:
        return ""
    for part in task.status.message.parts:
        if part.text:
            return part.text
    return ""


if __name__ == "__main__":
    asyncio.run(main())
