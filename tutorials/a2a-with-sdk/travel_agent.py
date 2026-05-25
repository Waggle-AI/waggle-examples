"""Travel Planner A2A Agent.

An agent that knows travel costs in local currencies and delegates currency
conversion to the Currency Agent via A2A protocol.

This demonstrates agent-to-agent communication: the Travel Agent discovers
the Currency Agent, sends it a conversion request, and uses the result to
answer the user's question.

Run: python travel_agent.py
(Requires currency_agent.py to be running on port 5001)
"""

from uuid import uuid4

import httpx
import uvicorn
from a2a.client import A2ACardResolver
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
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
    SendMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol
from starlette.applications import Starlette

# ---------------------------------------------------------------------------
# Travel knowledge base
# Prices are in local currencies - the kind of data a travel agent would know.
# ---------------------------------------------------------------------------

TRAVEL_ITEMS: dict[str, tuple[float, str]] = {
    "flight to paris": (420, "EUR"),
    "flight to tokyo": (185_000, "JPY"),
    "flight to london": (380, "GBP"),
    "flight to zurich": (450, "CHF"),
    "hotel in paris": (160, "EUR"),
    "hotel in tokyo": (18_000, "JPY"),
    "hotel in london": (195, "GBP"),
    "hotel in zurich": (280, "CHF"),
    "dinner in paris": (55, "EUR"),
    "dinner in tokyo": (3_500, "JPY"),
    "dinner in london": (40, "GBP"),
    "dinner in zurich": (65, "CHF"),
    "museum in paris": (17, "EUR"),
    "temple in tokyo": (500, "JPY"),
    "tour in london": (28, "GBP"),
    "boat on lake zurich": (15, "CHF"),
}

CURRENCY_AGENT_URL = "http://localhost:5001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_request(text: str) -> tuple[str | None, str | None]:
    """Parse a request like 'flight to paris in USD'.

    Returns (item_key, target_currency) or (None, None) if not understood.
    """
    text_lower = text.strip().lower()

    # Check for "in <CURRENCY>" suffix
    target_currency = None
    for currency in ("usd", "eur", "gbp", "jpy", "chf"):
        if text_lower.endswith(f" in {currency}"):
            target_currency = currency.upper()
            text_lower = text_lower[: -(len(currency) + 4)].strip()
            break

    # Match against known items
    for item_key in TRAVEL_ITEMS:
        if item_key in text_lower:
            return item_key, target_currency

    return None, None


def format_item_list() -> str:
    """Format the list of available travel items."""
    lines = ["Here's what I can look up for you:\n"]
    for item, (price, currency) in sorted(TRAVEL_ITEMS.items()):
        lines.append(f"  - {item}: {price:,.0f} {currency}")
    lines.append(
        '\nTip: add "in USD" (or EUR, GBP, JPY, CHF) to convert the price.'
    )
    return "\n".join(lines)


async def delegate_conversion(
    amount: float, source: str, target: str
) -> str | None:
    """Discover the Currency Agent and delegate a conversion.

    This is the core of agent-to-agent communication:
    1. Discover the agent by fetching its agent card
    2. Create a client from the card
    3. Send a message and read the response
    """
    # Step 1: Discover
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=CURRENCY_AGENT_URL,
        )
        card = await resolver.get_agent_card()

    # Step 2: Create client
    factory = ClientFactory(config=ClientConfig(streaming=False))
    client = factory.create(card)

    try:
        # Step 3: Send message
        message = Message(
            role=Role.ROLE_USER,
            parts=[Part(text=f"{amount:.2f} {source} to {target}")],
            message_id=uuid4().hex,
        )
        response = client.send_message(SendMessageRequest(message=message))

        # Step 4: Read result
        result_text = None
        async for stream_response in response:
            if not stream_response.HasField("task"):
                continue
            delegate_task = stream_response.task
            for artifact in delegate_task.artifacts:
                for part in artifact.parts:
                    if part.text:
                        result_text = part.text
        return result_text
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Agent executor
# ---------------------------------------------------------------------------


class TravelExecutor(AgentExecutor):
    """Handles travel queries, delegating currency conversion to another agent."""

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task = context.current_task or _new_task(context)
        await event_queue.enqueue_event(task)

        user_text = context.get_user_input()

        # Handle "list" or "help" commands
        if user_text.strip().lower() in ("list", "help", "menu", "items"):
            await self._complete(context, event_queue, format_item_list())
            return

        # Parse the request
        item_key, target_currency = parse_request(user_text)

        if item_key is None:
            await self._complete(
                context,
                event_queue,
                f"I don't recognize that item. {format_item_list()}",
            )
            return

        price, local_currency = TRAVEL_ITEMS[item_key]
        item_label = item_key.title()

        # If no conversion needed, return the local price
        if target_currency is None or target_currency == local_currency:
            await self._complete(
                context,
                event_queue,
                f"{item_label}: {price:,.0f} {local_currency}",
            )
            return

        # Delegation needed - tell the user what's happening
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    message=_agent_text_message(
                        f"Looking up {item_label} ({price:,.0f} "
                        f"{local_currency}). Asking the Currency Agent "
                        f"to convert to {target_currency}..."
                    ),
                ),
            )
        )

        # Delegate to the Currency Agent
        try:
            converted = await delegate_conversion(
                price, local_currency, target_currency
            )
        except Exception as exc:
            await self._complete(
                context,
                event_queue,
                f"{item_label}: {price:,.0f} {local_currency}\n"
                f"(Could not convert to {target_currency} "
                f"-- is the Currency Agent running? Error: {exc})",
            )
            return

        if converted:
            result = (
                f"{item_label}: {price:,.0f} {local_currency} "
                f"(~{converted})"
            )
        else:
            result = (
                f"{item_label}: {price:,.0f} {local_currency}\n"
                f"(Currency Agent did not return a result)"
            )

        await self._complete(context, event_queue, result)

    async def _complete(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        text: str,
    ) -> None:
        """Send a result artifact and mark the task completed."""
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=context.task_id or "",
                context_id=context.context_id or "",
                artifact=Artifact(
                    artifact_id=f"{context.task_id}-result",
                    name="travel_result",
                    parts=[Part(text=text)],
                ),
            )
        )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id or "",
                context_id=context.context_id or "",
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
        id="travel_prices",
        name="Travel Price Lookup",
        description=(
            "Looks up travel costs (flights, hotels, dining, activities) "
            "in cities around the world. Can convert prices to your "
            "preferred currency by delegating to a Currency Agent."
        ),
        tags=["travel", "prices", "flights", "hotels"],
        examples=[
            "flight to paris",
            "hotel in tokyo in USD",
            "dinner in london in EUR",
            "list",
        ],
    )

    agent_card = AgentCard(
        name="Travel Planner",
        description=(
            "Knows typical travel costs in cities worldwide and converts "
            "prices to your preferred currency using the Currency Agent."
        ),
        supported_interfaces=[
            AgentInterface(
                url="http://localhost:5002",
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            )
        ],
        provider=AgentProvider(
            organization="Waggle Examples",
            url="http://localhost:5002",
        ),
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=TravelExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    app = Starlette(
        routes=[
            *create_agent_card_routes(agent_card),
            *create_jsonrpc_routes(request_handler, "/", enable_v0_3_compat=True),
        ]
    )

    print("Travel Agent starting on http://localhost:5002")
    print(f"Will delegate currency conversion to {CURRENCY_AGENT_URL}")
    print()
    uvicorn.run(app, host="127.0.0.1", port=5002)

