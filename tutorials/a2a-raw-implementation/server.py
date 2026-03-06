import uuid
from copy import deepcopy
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from agent_card import AGENT_CARD
from converter import convert

app = Flask(__name__)

TASKS = {}

TASK_NOT_FOUND = -32001
TASK_NOT_CANCELABLE = -32002
UNSUPPORTED_OPERATION = -32003
CONTENT_TYPE_NOT_SUPPORTED = -32005

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


def utc_now():
    """Return an RFC 3339 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_message(role, text, context_id, task_id=None):
    """Create an A2A message object."""
    message = {
        "kind": "message",
        "messageId": str(uuid.uuid4()),
        "contextId": context_id,
        "role": role,
        "parts": [{"kind": "text", "text": text}],
    }
    if task_id is not None:
        message["taskId"] = task_id
    return message


def build_task(task_id, context_id, state, history, artifacts=None, status_text=None):
    """Create an A2A task object."""
    task = {
        "kind": "task",
        "id": task_id,
        "contextId": context_id,
        "status": {
            "state": state,
            "timestamp": utc_now(),
        },
        "history": history,
    }
    if artifacts:
        task["artifacts"] = artifacts
    if status_text:
        task["status"]["message"] = build_message("agent", status_text, context_id, task_id)
    return task


def jsonrpc_result(request_id, result):
    """Return a JSON-RPC success response."""
    return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})


def jsonrpc_error(request_id, code, message, http_status=400):
    """Return a JSON-RPC error response."""
    return (
        jsonify(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        ),
        http_status,
    )


def get_task_or_error(request_id, task_id):
    """Look up a task and return either it or a JSON-RPC error response."""
    task = TASKS.get(task_id)
    if task is None:
        return None, jsonrpc_error(request_id, TASK_NOT_FOUND, f"Task not found: {task_id}", 404)
    return task, None


@app.route("/.well-known/agent-card.json")
def agent_card():
    """Serve the agent card for A2A discovery."""
    return jsonify(AGENT_CARD)


@app.route("/", methods=["POST"])
def jsonrpc():
    """Handle A2A JSON-RPC 2.0 requests."""
    body = request.get_json(silent=True)

    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or "method" not in body:
        request_id = body.get("id") if isinstance(body, dict) else None
        return jsonrpc_error(request_id, -32600, "Invalid Request")

    method = body["method"]
    request_id = body.get("id")
    params = body.get("params", {})

    if method == "message/send":
        return handle_message_send(request_id, params)
    if method == "tasks/get":
        return handle_tasks_get(request_id, params)
    if method == "tasks/cancel":
        return handle_tasks_cancel(request_id, params)
    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def handle_message_send(request_id, params):
    """Handle the message/send method."""
    if not isinstance(params, dict):
        return jsonrpc_error(request_id, -32602, "params must be an object")

    message = params.get("message")
    if not isinstance(message, dict):
        return jsonrpc_error(request_id, -32602, "params.message is required")
    if message.get("kind") != "message":
        return jsonrpc_error(request_id, -32602, "params.message.kind must be 'message'")
    if not message.get("messageId"):
        return jsonrpc_error(request_id, -32602, "params.message.messageId is required")

    parts = message.get("parts")
    if not isinstance(parts, list) or not parts:
        return jsonrpc_error(request_id, -32602, "params.message.parts must be a non-empty list")

    configuration = params.get("configuration", {})
    if configuration and not isinstance(configuration, dict):
        return jsonrpc_error(request_id, -32602, "params.configuration must be an object")
    if configuration.get("pushNotificationConfig"):
        return jsonrpc_error(
            request_id,
            UNSUPPORTED_OPERATION,
            "Push notifications are not supported by this agent",
        )
    accepted_output_modes = configuration.get("acceptedOutputModes") or []
    if accepted_output_modes and "text/plain" not in accepted_output_modes:
        return jsonrpc_error(
            request_id,
            CONTENT_TYPE_NOT_SUPPORTED,
            "This agent only returns text/plain output",
        )

    text = ""
    for part in parts:
        if isinstance(part, dict) and part.get("kind") == "text":
            text = part.get("text", "").strip()
            if text:
                break
    if not text:
        return jsonrpc_error(request_id, -32602, "No text content in message")

    task_id = str(uuid.uuid4())
    context_id = message.get("contextId") or str(uuid.uuid4())
    normalized_message = deepcopy(message)
    normalized_message["contextId"] = context_id
    history = [normalized_message]

    try:
        result = convert(text)
    except ValueError as exc:
        agent_message = build_message("agent", str(exc), context_id, task_id)
        history.append(agent_message)
        task = build_task(
            task_id,
            context_id,
            "failed",
            history,
            status_text=str(exc),
        )
    else:
        success_text = "Conversion completed."
        history.append(build_message("agent", result, context_id, task_id))
        task = build_task(
            task_id,
            context_id,
            "completed",
            history,
            artifacts=[
                {
                    "artifactId": str(uuid.uuid4()),
                    "name": "conversion-result",
                    "parts": [{"kind": "text", "text": result}],
                }
            ],
            status_text=success_text,
        )

    TASKS[task_id] = deepcopy(task)
    return jsonrpc_result(request_id, task)


def handle_tasks_get(request_id, params):
    """Handle the tasks/get method."""
    if not isinstance(params, dict):
        return jsonrpc_error(request_id, -32602, "params must be an object")

    task_id = params.get("id")
    if not task_id:
        return jsonrpc_error(request_id, -32602, "params.id is required")

    task, error = get_task_or_error(request_id, task_id)
    if error is not None:
        return error

    task_copy = deepcopy(task)
    history_length = params.get("historyLength")
    if history_length is not None:
        if not isinstance(history_length, int) or history_length < 0:
            return jsonrpc_error(request_id, -32602, "params.historyLength must be a non-negative integer")
        if history_length > 0:
            task_copy["history"] = task_copy.get("history", [])[-history_length:]

    return jsonrpc_result(request_id, task_copy)


def handle_tasks_cancel(request_id, params):
    """Handle the tasks/cancel method."""
    if not isinstance(params, dict):
        return jsonrpc_error(request_id, -32602, "params must be an object")

    task_id = params.get("id")
    if not task_id:
        return jsonrpc_error(request_id, -32602, "params.id is required")

    task, error = get_task_or_error(request_id, task_id)
    if error is not None:
        return error

    state = task.get("status", {}).get("state")
    if state in TERMINAL_STATES:
        return jsonrpc_error(
            request_id,
            TASK_NOT_CANCELABLE,
            f"Task cannot be canceled from state: {state}",
            409,
        )

    canceled_message = "Task canceled."
    task["status"]["state"] = "canceled"
    task["status"]["timestamp"] = utc_now()
    task["status"]["message"] = build_message("agent", canceled_message, task["contextId"], task["id"])
    task.setdefault("history", []).append(
        build_message("agent", canceled_message, task["contextId"], task["id"])
    )
    TASKS[task_id] = deepcopy(task)
    return jsonrpc_result(request_id, task)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
