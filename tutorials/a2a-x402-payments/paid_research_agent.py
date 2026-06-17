"""Paid Research A2A Agent.

This example leaves the A2A agent card public and protects the JSON-RPC task
endpoint with x402. A client can discover the agent for free, but must pay
before a SendMessage request reaches the executor.

Run:
    python paid_research_agent.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol
from dotenv import load_dotenv
from starlette.applications import Starlette
from uvicorn import run
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer

load_dotenv()


@dataclass(frozen=True)
class Settings:
    pay_to: str
    price: str = "$0.001"
    network: str = "eip155:84532"
    facilitator_url: str = "https://x402.org/facilitator"
    host: str = "127.0.0.1"
    port: int = 4021

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.port}"


def load_settings() -> Settings:
    pay_to = os.environ.get("X402_PAY_TO")
    if not pay_to or pay_to == "0xYourReceivingWalletAddress":
        raise RuntimeError(
            "Set X402_PAY_TO to the EVM wallet address that should receive payments."
        )

    return Settings(
        pay_to=pay_to,
        price=os.environ.get("X402_PRICE", "$0.001"),
        network=os.environ.get("X402_NETWORK", "eip155:84532"),
        facilitator_url=os.environ.get(
            "X402_FACILITATOR_URL", "https://x402.org/facilitator"
        ),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "4021")),
    )


RESEARCH_NOTES = {
    "a2a": (
        "A2A is an agent-to-agent protocol for discovery and task exchange. "
        "An agent card describes what the agent can do, while JSON-RPC methods "
        "such as SendMessage let clients create tasks and receive artifacts."
    ),
    "x402": (
        "x402 is an HTTP-native payment protocol built around 402 Payment "
        "Required. A server returns payment requirements, the client signs a "
        "payment authorization, then retries the request with payment attached."
    ),
    "waggle": (
        "Waggle is a search and discovery layer for agents. It helps people and "
        "software find A2A agents, inspect their cards, and understand what they "
        "can do before invoking them."
    ),
}


def answer_query(text: str) -> str:
    query = text.strip().lower()
    for keyword, note in RESEARCH_NOTES.items():
        if keyword in query:
            return note

    topics = ", ".join(sorted(RESEARCH_NOTES))
    return (
        "I have short notes for a small tutorial knowledge base. "
        f"Try asking about one of these topics: {topics}."
    )


def agent_text_message(text: str) -> Message:
    return Message(
        message_id=uuid4().hex,
        role=Role.ROLE_AGENT,
        parts=[Part(text=text)],
    )


def new_task(context: RequestContext) -> Task:
    task = Task(
        id=context.task_id or uuid4().hex,
        context_id=context.context_id or uuid4().hex,
        status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
    )
    if context.message:
        task.history.append(context.message)
    return task


class PaidResearchExecutor(AgentExecutor):
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task = context.current_task or new_task(context)
        await event_queue.enqueue_event(task)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    message=agent_text_message("Preparing paid research note..."),
                ),
            )
        )

        result = answer_query(context.get_user_input())

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                artifact=Artifact(
                    artifact_id=f"{task.id}-research-note",
                    name="research_note",
                    parts=[Part(text=result)],
                ),
            )
        )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            )
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id or "",
                context_id=context.context_id or "",
                status=TaskStatus(
                    state=TaskState.TASK_STATE_CANCELED,
                    message=agent_text_message("Cancellation requested."),
                ),
            )
        )


def build_agent_card(settings: Settings) -> AgentCard:
    skill = AgentSkill(
        id="research_notes",
        name="Paid Research Notes",
        description=(
            "Returns short research notes for tutorial topics after an x402 "
            "payment."
        ),
        tags=["research", "a2a", "x402", "payments"],
        examples=[
            "Tell me about A2A",
            "Explain x402",
            "What is Waggle?",
        ],
    )

    return AgentCard(
        name="Paid Research Agent",
        description=(
            f"Returns short research notes. SendMessage calls cost "
            f"{settings.price} via x402 on {settings.network}."
        ),
        supported_interfaces=[
            AgentInterface(
                url=settings.base_url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            )
        ],
        provider=AgentProvider(
            organization="Waggle Examples",
            url=settings.base_url,
        ),
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
    )


def build_app(settings: Settings) -> Starlette:
    agent_card = build_agent_card(settings)
    request_handler = DefaultRequestHandler(
        agent_executor=PaidResearchExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    app = Starlette(
        routes=[
            *create_agent_card_routes(agent_card),
            *create_jsonrpc_routes(request_handler, "/", enable_v0_3_compat=True),
        ]
    )

    facilitator = HTTPFacilitatorClient(
        FacilitatorConfig(url=settings.facilitator_url)
    )
    resource_server = x402ResourceServer(facilitator)
    resource_server.register(settings.network, ExactEvmServerScheme())

    app.add_middleware(
        PaymentMiddlewareASGI,
        routes={
            "POST /": RouteConfig(
                accepts=[
                    PaymentOption(
                        scheme="exact",
                        pay_to=settings.pay_to,
                        price=settings.price,
                        network=settings.network,
                    )
                ],
                mime_type="application/json",
                description="Send a paid A2A task to the Paid Research Agent.",
            )
        },
        server=resource_server,
    )

    return app


if __name__ == "__main__":
    config = load_settings()
    print(f"Paid Research Agent starting on {config.base_url}")
    print(f"Agent card is public: {config.base_url}/.well-known/agent-card.json")
    print(f"A2A JSON-RPC endpoint is paid: POST {config.base_url}/")
    print(f"Price: {config.price} on {config.network}")
    print()
    run(build_app(config), host=config.host, port=config.port)
