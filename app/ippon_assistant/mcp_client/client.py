import os
import logging
from mcp.client.streamable_http import streamablehttp_client
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands.tools.mcp.mcp_client import MCPClient

logger = logging.getLogger(__name__)

# Gateway config (no auth)
GATEWAY_MCP_URL = os.environ.get(
    "GATEWAY_MCP_URL",
    "https://gateway-pricing-test-baixjwtpjs.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
)

# Local config
AWS_PROFILE = os.environ.get("AWS_PROFILE", "default")
AWS_REGION  = os.environ.get("AWS_REGION", "us-east-1")


def get_mcp_client() -> MCPClient:
    """
    Returns Gateway MCP client (HTTP, no auth) when GATEWAY_MCP_URL is set,
    otherwise falls back to local stdio (uvx).
    """
    if GATEWAY_MCP_URL:
        logger.info(f"Using Gateway MCP client: {GATEWAY_MCP_URL}")
        return MCPClient(lambda: streamablehttp_client(GATEWAY_MCP_URL))
    else:
        logger.info("Using local stdio MCP client (uvx)")
        server_params = StdioServerParameters(
            command="uvx",
            args=["awslabs.aws-pricing-mcp-server@latest"],
            env={
                "FASTMCP_LOG_LEVEL": "ERROR",
                "AWS_PROFILE": AWS_PROFILE,
                "AWS_REGION": AWS_REGION,
            },
        )
        return MCPClient(lambda: stdio_client(server_params))


def get_aws_pricing_mcp_client() -> MCPClient:
    return get_mcp_client()
