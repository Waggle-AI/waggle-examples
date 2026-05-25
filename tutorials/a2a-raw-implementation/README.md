# A2A Agent from Scratch

A minimal A2A 1.0 implementation in raw Python. It is built as a companion to the Waggle blog tutorial and intentionally keeps the business logic simple so the protocol details are easy to see.

## What's in here

| File | Description |
|------|-------------|
| `agent_card.py` | Agent card definition with `supportedInterfaces` and JSON-RPC endpoint metadata |
| `server.py` | Flask server with agent discovery plus `SendMessage`, `GetTask`, and `CancelTask` |
| `converter.py` | Unit conversion logic (temperature, distance, weight) |
| `client.py` | Console client that discovers the agent, sends requests, and fetches stored task state |

## Quick start

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Terminal 1: start the agent
python server.py

# Terminal 2: run the client
python client.py
```

## Test with curl

### Fetch the agent card

```bash
curl http://localhost:5000/.well-known/agent-card.json | python -m json.tool
```

### Send a conversion request

```bash
curl -X POST http://localhost:5000 \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-1",
        "contextId": "ctx-1",
        "role": "ROLE_USER",
        "parts": [{"text": "Convert 100 Fahrenheit to Celsius"}]
      },
      "configuration": {
        "acceptedOutputModes": ["text/plain"]
      }
    }
  }' | python -m json.tool
```

### Fetch the stored task

Replace `TASK_ID_HERE` with the task id returned by `SendMessage`.

```bash
curl -X POST http://localhost:5000 \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-2",
    "method": "GetTask",
    "params": {
      "id": "TASK_ID_HERE",
      "historyLength": 1
    }
  }' | python -m json.tool
```

### Try canceling a completed task

This implementation finishes work immediately, so cancellation returns the A2A `TaskNotCancelableError` code (`-32002`) once a task is already terminal.

```bash
curl -X POST http://localhost:5000 \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-3",
    "method": "CancelTask",
    "params": {
      "id": "TASK_ID_HERE"
    }
  }' | python -m json.tool
```

## Learn more

- [A2A for Beginners, Part 1](https://waggle.zone/blog/02_a2a-for-beginners-part-1)
- [A2A for Beginners, Part 2](https://waggle.zone/blog/03_a2a-for-beginners-part-2)
- [A2A Specification](https://a2a-protocol.org/latest/specification/)
- [Waggle](https://waggle.zone)
