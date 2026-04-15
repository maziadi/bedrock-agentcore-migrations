"""
Ippon Assistant — AWS Architecture Diagram
Run: pip install diagrams && python architecture.py
Output: architecture.png
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.client import User
from diagrams.aws.network import CloudFront, APIGateway
from diagrams.aws.storage import S3
from diagrams.aws.compute import Lambda
from diagrams.aws.ml import Bedrock, SagemakerModel
from diagrams.aws.security import IAMRole
from diagrams.aws.general import General
from diagrams.aws.management import SystemsManagerParameterStore

graph_attr = {
    "fontsize": "14",
    "bgcolor": "white",
    "pad": "0.5",
    "splines": "ortho",
    "nodesep": "0.8",
    "ranksep": "1.2",
}

with Diagram(
    "Ippon Assistant — AWS Architecture",
    filename="p1/docs/architecture",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    user = User("User\n(Browser)")

    # ── Frontend ──────────────────────────────────────────────────────
    with Cluster("Frontend (Static)"):
        cf  = CloudFront("CloudFront\nCDN + HTTPS")
        s3  = S3("S3\nindex.html")

    # ── Web Backend ───────────────────────────────────────────────────
    with Cluster("Web Backend"):
        apigw      = APIGateway("API Gateway\n/chat  /health")
        web_lambda = Lambda("Lambda\nweb_app_lambda.py\n(FastAPI + Mangum)")

    # ── AgentCore Runtime ─────────────────────────────────────────────
    with Cluster("Amazon Bedrock AgentCore"):
        runtime = Bedrock("AgentCore Runtime\nippon_assistant")
        llm     = SagemakerModel("LLM\nMistral Large 3\n(Bedrock)")

    # ── AgentCore Gateway ─────────────────────────────────────────────
    with Cluster("AgentCore Gateway"):
        gateway        = General("AgentCore Gateway\n(no auth)")
        pricing_lambda = Lambda("Lambda\naws-pricing-mcp\n(boto3 Pricing API)")

    # ── External ──────────────────────────────────────────────────────
    with Cluster("AWS Pricing"):
        pricing_api = General("AWS Price List API\npricing.us-east-1\n.amazonaws.com")

    # ── IAM ───────────────────────────────────────────────────────────
    iam = IAMRole("IAM Roles\n(SigV4 Auth)")

    # ── Request flow ──────────────────────────────────────────────────
    # 1. User → CloudFront
    user >> Edge(label="1. HTTPS request", color="black") >> cf

    # 2. CloudFront → S3 (static) or API GW (dynamic)
    cf >> Edge(label="2a. GET /\n(static)", color="steelblue", style="dashed") >> s3
    cf >> Edge(label="2b. POST /chat\n(dynamic)", color="darkorange") >> apigw

    # 3. API GW → Lambda
    apigw >> Edge(label="3. invoke", color="darkorange") >> web_lambda

    # 4. Lambda → AgentCore Runtime (SigV4)
    web_lambda >> Edge(label="4. SigV4\nHTTP POST", color="red") >> runtime
    web_lambda >> Edge(label="IAM auth", color="gray", style="dashed") >> iam

    # 5. AgentCore Runtime → LLM
    runtime >> Edge(label="5. ConverseStream\n(tool use)", color="purple") >> llm

    # 6. AgentCore Runtime → Gateway
    runtime >> Edge(label="6. MCP\ntools/call", color="green") >> gateway

    # 7. Gateway → Lambda Pricing
    gateway >> Edge(label="7. invoke", color="green") >> pricing_lambda

    # 8. Lambda Pricing → AWS Pricing API
    pricing_lambda >> Edge(label="8. GetProducts\n(boto3)", color="teal") >> pricing_api

    # 9. Response flows back
    pricing_api >> Edge(label="9. pricing data", color="teal", style="dashed") >> pricing_lambda
    pricing_lambda >> Edge(label="10. tool result", color="green", style="dashed") >> gateway
    gateway >> Edge(label="11. MCP response", color="green", style="dashed") >> runtime
    llm >> Edge(label="12. final answer", color="purple", style="dashed") >> runtime
    runtime >> Edge(label="13. streamed\nresponse", color="red", style="dashed") >> web_lambda
    web_lambda >> Edge(label="14. JSON response", color="darkorange", style="dashed") >> apigw
    apigw >> Edge(label="15. HTTP 200", color="darkorange", style="dashed") >> cf
    cf >> Edge(label="16. rendered\nresponse", color="black", style="dashed") >> user
