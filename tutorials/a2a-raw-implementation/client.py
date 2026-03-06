import uuid

import requests


def discover(base_url):
    """Fetch the agent card from a known URL."""
    card_url = f"{base_url}/.well-known/agent-card.json"
    response = requests.get(card_url, timeout=10)
    response.raise_for_status()
    return response.json()


def get_jsonrpc_endpoint(card):
    """Return the JSON-RPC endpoint from the agent card."""
    if card.get("preferredTransport") == "JSONRPC":
        return card["url"]

    for interface in card.get("additionalInterfaces", []):
        if interface.get("transport") == "JSONRPC":
            return interface["url"]

    raise ValueError("Agent card does not declare a JSON-RPC endpoint")


def post_jsonrpc(agent_url, payload):
    """POST a JSON-RPC request and return the decoded response."""
    response = requests.post(agent_url, json=payload, timeout=10)
    try:
        result = response.json()
    except ValueError:
        response.raise_for_status()
        raise

    if response.status_code >= 500:
        response.raise_for_status()
    return result


def send_message(agent_url, text, context_id=None):
    """Send a message/send request and return the task response."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": str(uuid.uuid4()),
                "contextId": context_id or str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            },
            "configuration": {
                "acceptedOutputModes": ["text/plain"],
            },
        },
    }
    return post_jsonrpc(agent_url, payload)


def get_task(agent_url, task_id, history_length=None):
    """Fetch the latest state for a task."""
    params = {"id": task_id}
    if history_length is not None:
        params["historyLength"] = history_length

    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tasks/get",
        "params": params,
    }
    return post_jsonrpc(agent_url, payload)


def cancel_task(agent_url, task_id):
    """Cancel a task."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tasks/cancel",
        "params": {"id": task_id},
    }
    return post_jsonrpc(agent_url, payload)


def print_response(result):
    """Parse and display an A2A task response."""
    if "error" in result:
        print(f"Error {result['error']['code']}: {result['error']['message']}")
        return

    task = result.get("result", {})
    state = task.get("status", {}).get("state")

    if state == "completed":
        for artifact in task.get("artifacts", []):
            for part in artifact.get("parts", []):
                if part.get("kind") == "text":
                    print(part["text"])
    elif state == "failed":
        status_message = task.get("status", {}).get("message", {})
        for part in status_message.get("parts", []):
            if part.get("kind") == "text":
                print(f"Agent error: {part['text']}")
                return
        print("Agent error: task failed")
    else:
        print(f"Task state: {state}")


def main():
    base_url = "http://localhost:5000"

    print(f"Discovering agent at {base_url}...")
    card = discover(base_url)
    agent_url = get_jsonrpc_endpoint(card)
    print(f"Found: {card['name']} - {card['description']}")
    print(f"Transport: {card['preferredTransport']} -> {agent_url}")
    print(f"Skills: {', '.join(s['name'] for s in card['skills'])}")
    print()

    print("Type a conversion request (or 'quit' to exit):")
    print("Examples: 'Convert 100 F to C', '5 miles to km', '150 lbs to kg'")
    print()

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not text or text.lower() in ("quit", "exit"):
            break

        result = send_message(agent_url, text)
        print_response(result)

        task = result.get("result", {})
        if task.get("id"):
            latest = get_task(agent_url, task["id"], history_length=1)
            print(f"Stored task state: {latest.get('result', {}).get('status', {}).get('state')}")
        print()


if __name__ == "__main__":
    main()
