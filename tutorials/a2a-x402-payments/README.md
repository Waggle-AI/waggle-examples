# A2A Agent with x402 Payments

A tutorial demonstrating how to protect an A2A JSON-RPC endpoint with x402 payments while leaving the agent card public for discovery.

Companion blog post: [Build an A2A Agent That Accepts x402 Payments](https://waggle.zone/blog/06_a2a-agent-with-x402-payments)

## What's Here

| File | Description |
|------|-------------|
| `paid_research_agent.py` | An A2A SDK agent whose `POST /` JSON-RPC endpoint requires x402 payment |
| `paid_client.py` | A client that sends a paid A2A `SendMessage` request using x402's `httpx` integration |
| `.env.example` | Example server and client configuration |
| `requirements.txt` | Python dependencies |

## Quick Start

You need Python 3.10+.

```bash
cd tutorials/a2a-x402-payments
python -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```bash
X402_PAY_TO=0xYourReceivingWalletAddress
EVM_PRIVATE_KEY=0xYourBaseSepoliaPrivateKey
```

For testnet payments, your client wallet needs Base Sepolia ETH for gas and Base Sepolia testnet USDC.

Base Sepolia is a test version of Base, Coinbase's Ethereum Layer 2 network. The ETH and USDC on Base Sepolia are faucet tokens for development and QA, not real funds. This tutorial uses the testnet path so you can verify the x402 payment challenge, facilitator, wallet signature, and A2A request flow without spending real money.

Useful references:

- [CDP supported networks: mainnets vs. testnets](https://docs.cdp.coinbase.com/get-started/supported-networks#mainnets-vs-testnets)
- [x402 network support and CAIP-2 identifiers](https://docs.cdp.coinbase.com/x402/network-support)
- [CDP faucet quickstart](https://docs.cdp.coinbase.com/faucets/introduction/quickstart)

Start the agent:

```bash
python paid_research_agent.py
```

In another terminal, discover the public agent card:

```bash
curl http://localhost:4021/.well-known/agent-card.json | python -m json.tool
```

Call the paid endpoint without payment to see the `402 Payment Required` challenge:

```bash
curl -i -X POST http://localhost:4021 \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc":"2.0","id":"req-1","method":"SendMessage","params":{"message":{"messageId":"msg-1","role":"ROLE_USER","parts":[{"text":"Tell me about A2A"}]},"configuration":{"acceptedOutputModes":["text/plain"]}}}'
```

Then run the x402-aware paid client:

```bash
python paid_client.py "Tell me about x402"
```

## Notes

This is an educational example, not production infrastructure. Production paid agents should add persistent task storage, stronger observability, spending policy controls, production facilitator credentials, and a clear refund/support process.
