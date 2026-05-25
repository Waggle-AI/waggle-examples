# Implicit Geometry Agent - Local

A self-contained A2A agent that generates GLB meshes for implicit geometry prompts.

This example limits raw GLB responses to 4 MB so the same behavior works in the AWS Lambda deployment example.

It uses:

- the official `a2a-sdk` for A2A discovery, tasks, and artifacts
- OpenAI structured output for parameter extraction
- NumPy and scikit-image for scalar fields and marching cubes
- a small built-in GLB writer for returning `model/gltf-binary`

## Quick start

```bash
cd examples/implicit-geometry-local
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Set your OpenAI key:

On Mac / Linux:

```bash
export OPENAI_API_KEY=your-openai-api-key
export OPENAI_MODEL=gpt-5-mini
```

Windows CMD:

```bash
set OPENAI_API_KEY=your-openai-api-key
set OPENAI_MODEL=gpt-5-mini
```

On PowerShell:

```powershell
$env:OPENAI_API_KEY="your-openai-api-key"
$env:OPENAI_MODEL="gpt-5-mini"
```

### Start the agent:

```bash
python server.py
```

### In another terminal, run the client:

```bash
python client.py "Generate a gyroid surface"
python client.py "Create a rainbow Schwarz P surface with 3 periods"
python client.py "Surface of x^2 + y^2 + z^2 = 4"
python client.py "Plot z = sin(x) * cos(y)"
```

Returned GLB files are written to `outputs/`.
You can view them in the model-viewer editor: https://modelviewer.dev/editor/.

## Agent card

```bash
curl http://localhost:5010/.well-known/agent-card.json | python -m json.tool
```

## Raw A2A request

```bash
curl -X POST http://localhost:5010 \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "ROLE_USER",
        "parts": [{"text": "Generate a gyroid surface"}]
      }
    }
  }' | python -m json.tool
```

## Supported prompts

The extractor maps natural language into:

- `surface_type`: `gyroid`, `schwarz_p`, `diamond`, `neovius`, `lidinoid`, `custom_explicit`, `custom_implicit`
- `periods`: `1` to `4`
- `resolution`: `32` to `72`
- `iso_level`: `-1.0` to `1.0`
- `expression`: a safe Python math expression for custom surfaces
- `coloring`: `normal`, `height`, `radial`, `curvature`, `none`
- `colormap`: `viridis`, `plasma`, `coolwarm`, `rainbow`

Custom expressions are AST-validated. Attribute access, imports, strings, large constants, and variable exponents are rejected.
