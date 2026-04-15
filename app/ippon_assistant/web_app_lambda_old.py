"""
Lambda chatbot web server — FastAPI + Mangum (no streaming)

Deployed on AWS Lambda + API Gateway + CloudFront.
The /chat endpoint collects the full response then returns it as JSON.

Handler: web_app_lambda.handler
"""
import os
import re
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from mangum import Mangum

# ── config ────────────────────────────────────────────────────────────
AGENTCORE_RUNTIME_URL = os.environ.get(
    "AGENTCORE_RUNTIME_URL",
    "https://bedrock-agentcore.us-east-1.amazonaws.com"
    "/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A800881206773"
    "%3Aruntime%2FIpponAWSAssistant_ippon_assistant-D1SGcJ7zxc/invocations"
)

# CloudFront URL for serving static index.html
CLOUDFRONT_URL = os.environ.get("CLOUDFRONT_URL", "")

# ── thinking tag filter ───────────────────────────────────────────────
_THINKING_RE = re.compile(r'<thinking>.*?</thinking>', re.DOTALL)

def _strip_thinking(text: str) -> str:
    return _THINKING_RE.sub('', text).lstrip('\n')

# ── app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Ippon Assistant - AWS Cost Estimator")

# index.html is served from S3/CloudFront in production
# kept here for local testing fallback
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
async def index():
    # In production, serve index.html from Lambda package
    # (CloudFront routes / to API Gateway which serves it here)
    html_file = Path(__file__).parent / "static" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    # Fallback redirect to CloudFront static
    if CLOUDFRONT_URL:
        return RedirectResponse(url=f"{CLOUDFRONT_URL}/static/index.html")
    return HTMLResponse(content="<h1>Ippon Assistant</h1><p>Static files not found.</p>")


# ── AgentCore invocation (non-streaming) ─────────────────────────────

async def _invoke_agentcore(prompt: str) -> str:
    """Invoke AgentCore Runtime and collect full response."""
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    region = os.environ.get("AWS_REGION", "us-east-1")

    payload = json.dumps({"prompt": prompt}).encode()

    request = AWSRequest(
        method="POST",
        url=AGENTCORE_RUNTIME_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials, "bedrock-agentcore", region).add_auth(request)
    signed_headers = dict(request.headers)

    full_response = ""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            AGENTCORE_RUNTIME_URL,
            content=payload,
            headers=signed_headers,
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                chunk = chunk.strip()
                try:
                    decoded = json.loads(chunk)
                    if isinstance(decoded, str):
                        full_response += decoded
                    elif isinstance(decoded, dict):
                        full_response += decoded.get("data", decoded.get("text", str(decoded)))
                    else:
                        full_response += str(decoded)
                except (json.JSONDecodeError, ValueError):
                    full_response += chunk

    return _strip_thinking(full_response)


# ── /chat endpoint ────────────────────────────────────────────────────

@app.post("/chat")
async def chat(
    message: str = Form(...),
    spec_file: UploadFile | None = File(default=None),
):
    """Returns full agent response as JSON (no streaming)."""
    prompt = message

    if spec_file and spec_file.filename:
        spec_text = (await spec_file.read()).decode("utf-8", errors="replace")
        prompt = (
            f"Here is the infrastructure spec file ({spec_file.filename}):\n\n"
            f"```\n{spec_text}\n```\n\n"
            f"User request: {message}"
        )

    try:
        response_text = await _invoke_agentcore(prompt)
        return JSONResponse({"response": response_text, "error": None})
    except Exception as e:
        return JSONResponse({"response": None, "error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Lambda handler ────────────────────────────────────────────────────
handler = Mangum(app, lifespan="off")
