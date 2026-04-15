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
from fastapi.responses import HTMLResponse, JSONResponse
from mangum import Mangum

# ── config ────────────────────────────────────────────────────────────
AGENTCORE_RUNTIME_URL = os.environ.get(
    "AGENTCORE_RUNTIME_URL",
    "https://bedrock-agentcore.us-east-1.amazonaws.com"
    "/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A800881206773"
    "%3Aruntime%2FIpponAWSAssistant_ippon_assistant-D1SGcJ7zxc/invocations"
)

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
    html_file = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


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

    parts: list[str] = []
    buf = ""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            AGENTCORE_RUNTIME_URL,
            content=payload,
            headers=signed_headers,
        ) as response:
            response.raise_for_status()
            async for raw_chunk in response.aiter_text():
                if not raw_chunk:
                    continue
                buf += raw_chunk
                lines = buf.split("\n")
                buf = lines.pop()  # Keep incomplete last line in buffer
                for line in lines:
                    if line.startswith("data: "):
                        content = line[6:]
                        if content and content != "[DONE]":
                            parts.append(content)
    # Flush remaining buffer
    if buf.startswith("data: "):
        content = buf[6:]
        if content and content != "[DONE]":
            parts.append(content)

    return _strip_thinking("".join(parts))


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
