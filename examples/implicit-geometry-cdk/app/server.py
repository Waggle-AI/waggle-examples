from __future__ import annotations

import os
import asyncio
import base64
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
from starlette.applications import Starlette

from extractor import ExtractionError, extract_surface_request
from geometry import GeometryError, generate_geometry

try:
    from mangum import Mangum
except ImportError:
    Mangum = None


DEFAULT_PORT = 5010


def public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{os.environ.get('PORT', DEFAULT_PORT)}").rstrip("/")


def build_agent_card() -> AgentCard:
    base_url = public_base_url()
    return AgentCard(
        name="Implicit Geometry Agent",
        description=(
            "Generates GLB meshes for implicit mathematical surfaces, including "
            "gyroid, Schwarz P, diamond, Neovius, lidinoid, and custom equations."
        ),
        supported_interfaces=[
            AgentInterface(
                url=base_url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            )
        ],
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "model/gltf-binary"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="implicit_geometry",
                name="Implicit Geometry",
                description="Generate a 3D GLB mesh from a natural-language surface request.",
                tags=["geometry", "3d", "mesh", "implicit", "glb"],
                examples=[
                    "Generate a gyroid surface",
                    "Create a rainbow Schwarz P surface with 3 periods",
                    "Surface of x^2 + y^2 + z^2 = 4",
                    "Plot z = sin(x) * cos(y)",
                ],
            )
        ],
        provider=AgentProvider(organization="Waggle Examples", url=base_url),
    )


class GeometryExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or _new_task(context)
        await event_queue.enqueue_event(task)

        user_text = context.get_user_input().strip()
        if not user_text:
            await self._fail(context, event_queue, "Send a text prompt describing the surface to generate.")
            return

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    message=_agent_text_message("Extracting geometry parameters..."),
                ),
            )
        )

        try:
            result = await asyncio.to_thread(_extract_and_generate, user_text)
        except (ExtractionError, GeometryError) as exc:
            await self._fail(context, event_queue, str(exc))
            return
        except Exception as exc:
            await self._fail(context, event_queue, f"Geometry generation failed: {exc}")
            return

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                artifact=Artifact(
                    artifact_id=f"{task.id}-geometry",
                    name="implicit_geometry_result",
                    parts=[
                        Part(text=result.summary),
                        Part(
                            raw=base64.b64decode(result.base64_bytes),
                            media_type=result.mime_type,
                            filename=result.file_name,
                        ),
                    ],
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

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_CANCELED,
                    message=_agent_text_message("Cancellation requested."),
                ),
            )
        )

    async def _fail(self, context: RequestContext, event_queue: EventQueue, message: str) -> None:
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id or "",
                context_id=context.context_id or "",
                status=TaskStatus(
                    state=TaskState.TASK_STATE_FAILED,
                    message=_agent_text_message(message),
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


def _extract_and_generate(user_text: str):
    request = extract_surface_request(user_text)
    return generate_geometry(request)


agent_card = build_agent_card()
request_handler = DefaultRequestHandler(
    agent_executor=GeometryExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)

asgi_app = Starlette(
    routes=[
        *create_agent_card_routes(agent_card),
        *create_jsonrpc_routes(request_handler, "/", enable_v0_3_compat=True),
    ]
)
handler = Mangum(asgi_app) if Mangum is not None else None


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", DEFAULT_PORT))
    print(f"Implicit Geometry Agent starting on http://localhost:{port}")
    print("Requires OPENAI_API_KEY in the environment.")
    uvicorn.run(asgi_app, host="127.0.0.1", port=port)
