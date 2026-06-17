"""x402-aware client for the Paid Research A2A Agent.

Run:
    python paid_client.py "Tell me about x402"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from uuid import uuid4

from dotenv import load_dotenv
from eth_account import Account
from x402 import x402Client
from x402.http import x402HTTPClient
from x402.http.clients import x402HttpxClient
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

load_dotenv()


def build_send_message(text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": f"req-{uuid4().hex}",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": f"msg-{uuid4().hex}",
                "role": "ROLE_USER",
                "parts": [{"text": text}],
            },
            "configuration": {
                "acceptedOutputModes": ["text/plain"],
            },
        },
    }


def print_artifacts(payload: dict) -> None:
    task = payload.get("result", {}).get("task")
    if not task:
        print(json.dumps(payload, indent=2))
        return

    print(f"Task state: {task.get('status', {}).get('state')}")
    for artifact in task.get("artifacts", []):
        for part in artifact.get("parts", []):
            if "text" in part:
                print(part["text"])


async def main() -> None:
    private_key = os.environ.get("EVM_PRIVATE_KEY")
    if not private_key or private_key == "0xYourBaseSepoliaPrivateKey":
        raise RuntimeError(
            "Set EVM_PRIVATE_KEY to a testnet wallet with Base Sepolia ETH and USDC."
        )

    agent_url = os.environ.get("AGENT_URL", "http://localhost:4021").rstrip("/")
    query = " ".join(sys.argv[1:]) or "Tell me about x402"

    client = x402Client()
    account = Account.from_key(private_key)
    register_exact_evm_client(client, EthAccountSigner(account))

    payment_helper = x402HTTPClient(client)

    async with x402HttpxClient(client) as http:
        response = await http.post(
            f"{agent_url}/",
            headers={
                "Content-Type": "application/json",
                "A2A-Version": "1.0",
            },
            json=build_send_message(query),
            timeout=60,
        )
        await response.aread()
        response.raise_for_status()

        settlement = payment_helper.get_payment_settle_response(
            lambda name: response.headers.get(name)
        )
        if settlement:
            print(f"Payment settled: {settlement}")

        print_artifacts(response.json())


if __name__ == "__main__":
    asyncio.run(main())
