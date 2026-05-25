# Implicit Geometry Agent - AWS CDK

Deploy the implicit geometry A2A agent to your own AWS account as a Lambda container behind API Gateway.

AWS CDK is an infrastructure-as-code toolkit for defining cloud resources in a programming language and deploying them with CloudFormation. This example uses CDK so you can deploy the Lambda, API Gateway, and permissions from one reproducible Python app; read more at https://aws.amazon.com/cdk/.

This example is for educational purposes and workshops only. It is not production-ready and should not be deployed as-is for public or commercial use. The deployed API is public and unauthenticated, so anyone with the URL can invoke your Lambda function and use the configured OpenAI key.

This example is self-contained. The Lambda image includes the A2A server, OpenAI extractor, geometry code, and GLB writer.

## Prerequisites

- Python 3.10+
- Docker
- AWS credentials configured for your target account
- AWS CDK v2
- An OpenAI API key

## Store the OpenAI key

Create a Secrets Manager secret in the target AWS account:

```bash
aws secretsmanager create-secret \
  --name implicit-geometry/openai-api-key \
  --secret-string "your-openai-api-key"
```

You can also store JSON:

```bash
aws secretsmanager create-secret \
  --name implicit-geometry/openai-api-key \
  --secret-string '{"OPENAI_API_KEY":"your-openai-api-key"}'
```

## Deploy

```bash
cd examples/implicit-geometry-cdk
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

cdk bootstrap
cdk deploy
```

To use a different secret name or model:

```bash
cdk deploy \
  -c openaiSecretName=my/openai/secret \
  -c openaiModel=gpt-5-mini
```

The stack outputs:

- `AgentUrl`
- `AgentCardUrl`

Set `AGENT_URL` from the `AgentUrl` output before running the test commands:

```bash
export AGENT_URL=https://your-api-id.execute-api.your-region.amazonaws.com
```

Raw GLB responses are capped at 4 MB to stay below Lambda's synchronous response payload limit after base64 and JSON encoding.

You can view returned `.glb` files in the model-viewer editor: https://modelviewer.dev/editor/.

## Test

Fetch the agent card:

```bash
curl "$AGENT_URL/.well-known/agent-card.json" | python -m json.tool
```

Send an A2A message:

```bash
curl -X POST "$AGENT_URL" \
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

## Destroy

```bash
cdk destroy
```

The CDK stack does not create or delete your OpenAI secret.
