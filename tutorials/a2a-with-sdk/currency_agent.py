"""Currency Converter A2A Agent.

A simple agent that converts between currencies using static exchange rates.
Accepts messages like "100 USD to EUR" and returns the converted amount.

Run: python currency_agent.py
"""

import re

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.message import new_agent_text_message
from a2a.utils.task import new_task

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
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                final=False,
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        "Converting currency..."
                    ),
                ),
            )
        )

        # Extract user text from the message parts
        user_text = ""
        for part in context.message.parts:
            if hasattr(part, "root"):
                part = part.root
            if isinstance(part, TextPart):
                user_text = part.text
                break

        result = convert(user_text)

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                artifact=Artifact(
                    artifactId=f"{context.task_id}-result",
                    name="conversion_result",
                    parts=[TextPart(text=result)],
                ),
            )
        )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                final=True,
                status=TaskStatus(state=TaskState.completed),
            )
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception("cancel not supported")


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
        url="http://localhost:5001",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=CurrencyExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    print("Currency Agent starting on http://localhost:5001")
    print("Skills: Currency Conversion (USD, EUR, GBP, JPY, CHF)")
    print()
    uvicorn.run(app.build(), host="127.0.0.1", port=5001)
