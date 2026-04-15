from strands import Agent
from model.load import load_model
from mcp_client.client import get_mcp_client

_mcp_client = None
_agent = None


def get_or_create_agent() -> Agent:
    global _agent, _mcp_client
    if _agent is None:
        _mcp_client = get_mcp_client()
        _agent = Agent(
            model=load_model(),
            system_prompt="""
You are an AWS cost estimation expert. Your job is to analyze infrastructure
specifications provided by the user and produce a detailed cost estimate.

When the user provides a spec file or describes their infrastructure:
1. Identify all AWS services mentioned (EC2, RDS, S3, Lambda, ECS, etc.)
2. Use the AWS Pricing tools to fetch real-time pricing for each service
3. Calculate monthly and annual cost estimates
4. Present results as a clear summary table with:
   - Service name
   - Configuration (instance type, region, size, etc.)
   - Unit price
   - Quantity / usage
   - Monthly cost
   - Annual cost
5. Provide a TOTAL at the bottom
6. Add cost optimization tips when relevant

Always use us-east-1 pricing unless the user specifies a different region.
Be precise and show your calculations. If information is missing, ask the user.
""",
            tools=[_mcp_client],
        )
    return _agent
