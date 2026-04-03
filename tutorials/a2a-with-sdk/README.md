# A2A with the Official SDK

A tutorial demonstrating how to build A2A agents using the official [a2a-sdk](https://pypi.org/project/a2a-sdk/) and make two agents communicate with each other.

Companion blog post: [A2A for Beginners, Part 3: Building an Agent the Smart Way](https://waggle.zone/blog/04_a2a-for-beginners-part-3)

## What's Here

| File | Description |
|------|-------------|
| `currency_agent.py` | An A2A agent that converts between currencies (USD, EUR, GBP, JPY, CHF) |
| `travel_agent.py` | An A2A agent that knows travel prices and **delegates** currency conversion to the Currency Agent |
| `client.py` | A client that discovers and talks to the Travel Agent |

## Quick Start

You need Python 3.10+.

```bash
cd tutorials/a2a-with-sdk
python -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Then open **three terminals**:

```bash
# Terminal 1: Start the Currency Agent
python currency_agent.py

# Terminal 2: Start the Travel Agent
python travel_agent.py

# Terminal 3: Run the client
python client.py            # Interactive mode
python client.py --demo     # Scripted demo
```

## Example Output

```
> flight to paris in USD
  Flight To Paris: 420 EUR (~457.80 USD)

> hotel in tokyo in USD
  Hotel In Tokyo: 18,000 JPY (~120.60 USD)

> dinner in london in EUR
  Dinner In London: 40 GBP (~46.40 EUR)
```

When you ask for a price in a different currency, the Travel Agent discovers the Currency Agent at `http://localhost:5001`, sends it a conversion request over A2A, and returns the result.
