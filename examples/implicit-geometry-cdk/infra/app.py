from __future__ import annotations

from pathlib import Path

from aws_cdk import App, CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class ImplicitGeometryAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        secret_name = self.node.try_get_context("openaiSecretName")
        model = self.node.try_get_context("openaiModel") or "gpt-5-mini"

        if not secret_name:
            raise ValueError("Set context openaiSecretName to the Secrets Manager secret name.")

        app_dir = Path(__file__).resolve().parents[1] / "app"
        openai_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "OpenAiApiKey",
            secret_name,
        )

        agent_function = lambda_.DockerImageFunction(
            self,
            "ImplicitGeometryAgentFunction",
            code=lambda_.DockerImageCode.from_image_asset(str(app_dir)),
            architecture=lambda_.Architecture.X86_64,
            memory_size=2048,
            timeout=Duration.seconds(60),
            environment={
                "OPENAI_SECRET_NAME": secret_name,
                "OPENAI_MODEL": model,
            },
        )
        openai_secret.grant_read(agent_function)

        integration = integrations.HttpLambdaIntegration(
            "ImplicitGeometryAgentIntegration",
            agent_function,
        )
        api = apigwv2.HttpApi(
            self,
            "ImplicitGeometryAgentApi",
            default_integration=integration,
        )

        agent_function.add_environment("PUBLIC_BASE_URL", api.api_endpoint)

        CfnOutput(self, "AgentUrl", value=api.api_endpoint)
        CfnOutput(self, "AgentCardUrl", value=f"{api.api_endpoint}/.well-known/agent-card.json")


app = App()
ImplicitGeometryAgentStack(app, "ImplicitGeometryAgentStack")
app.synth()
