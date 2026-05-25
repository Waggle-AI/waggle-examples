"""Currency Converter A2A Agent.

A simple agent that converts between currencies using static exchange rates.
Accepts messages like "100 USD to EUR" and returns the converted amount.

Run: python currency_agent.py
"""

import re
from uuid import uuid4

import uvicorn
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
from starlette.applications import Starlette

# ---------------------------------------------------------------------------
# Exchange rates (static, for demonstration)
# ---------------------------------------------------------------------------

RATES: dict[tuple[str, str], float] = {
    ("USD", "EUR"): 0.92,
    ("USD", "GBP"): 0.79,
    ("USD", "JPY"): 149.50,
    ("USD", "CHF"): 0.88,
    ("EUR", "USD"): 1.09,
    ("EUR", "GBP"): 0.86,
    ("EUR", "JPY"): 162.50,
    ("EUR", "CHF"): 0.96,
    ("GBP", "USD"): 1.27,
    ("GBP", "EUR"): 1.16,
    ("GBP", "JPY"): 189.50,
    ("GBP", "CHF"): 1.12,
    ("JPY", "USD"): 0.0067,
    ("JPY", "EUR"): 0.0062,
    ("JPY", "GBP"): 0.0053,
    ("JPY", "CHF"): 0.0059,
    ("CHF", "USD"): 1.14,
    ("CHF", "EUR"): 1.04,
    ("CHF", "GBP"): 0.89,
    ("CHF", "JPY"): 170.0,
}

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF"}

# ---------------------------------------------------------------------------
# Conversion logic
# ---------------------------------------------------------------------------

PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*([A-Za-z]{3})\s+(?:to\s+)?([A-Za-z]{3})",
    re.IGNORECASE,
)


def convert(text: str) -> str:
    """Parse a conversion request and return the result."""
    match = PATTERN.search(text)
    if not match:
        return (
            "I didn't understand that. "
            "Try something like: 100 USD to EUR"
        )

    amount = float(match.group(1))
    source = match.group(2).upper()
    target = match.group(3).upper()

    if source not in SUPPORTED_CURRENCIES:
        return f"Unknown currency: {source}"
    if target not in SUPPORTED_CURRENCIES:
        return f"Unknown currency: {target}"
    if source == target:
        return f"{amount:.2f} {source}"

    rate = RATES.get((source, target))
    if rate is None:
        return f"No rate available for {source} -> {target}"

    converted = amount * rate
    return f"{converted:,.2f} {target}"


# ---------------------------------------------------------------------------
# Agent executor
# ---------------------------------------------------------------------------


class CurrencyExecutor(AgentExecutor):
    """Handles incoming messages by converting currencies."""

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task = context.current_task or _new_task(context)
        await event_queue.enqueue_event(task)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    message=_agent_text_message(
                        "Converting currency..."
                    ),
                ),
            )
        )

        result = convert(context.get_user_input())

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                artifact=Artifact(
                    artifact_id=f"{task.id}-result",
                    name="conversion_result",
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
                    message=_agent_text_message("Cancellation requested."),
                ),
            )
        )


def _agent_text_message(text: str) -> Message:
    return Message(
        message_id=uuid4().hex,
        role=Role.ROLE_AGENT,
        parts=[Part(text=text)],
    )


def _new_task(context: RequestContext) -> Task:
    task = Task(
        id=context.task_id or uuid4().hex,
        context_id=context.context_id or uuid4().hex,
        status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
    )
    if context.message:
        task.history.append(context.message)
    return task


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    skill = AgentSkill(
        id="currency_conversion",
        name="Currency Conversion",
        description="Converts an amount from one currency to another.",
        tags=["currency", "finance", "conversion"],
        examples=[
            "100 USD to EUR",
            "5000 JPY to GBP",
            "250 CHF to USD",
        ],
    )

    agent_card = AgentCard(
        name="Currency Converter",
        description=(
            "Converts between major currencies (USD, EUR, GBP, JPY, CHF) "
            "using current exchange rates."
        ),
        supported_interfaces=[
            AgentInterface(
                url="http://localhost:5001",
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            )
        ],
        provider=AgentProvider(
            organization="Waggle Examples",
            url="http://localhost:5001",
        ),
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=CurrencyExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    app = Starlette(
        routes=[
            *create_agent_card_routes(agent_card),
            *create_jsonrpc_routes(request_handler, "/", enable_v0_3_compat=True),
        ]
    )

    print("Currency Agent starting on http://localhost:5001")
    print("Skills: Currency Conversion (USD, EUR, GBP, JPY, CHF)")
    print()
    uvicorn.run(app, host="127.0.0.1", port=5001)
