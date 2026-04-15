"""
Local chatbot web server — FastAPI + SSE streaming

Modes (controlled by USE_AGENTCORE env var):
  - USE_AGENTCORE=true  → invoke AgentCore Runtime on AWS
  - USE_AGENTCORE=false → use local Strands agent (default)

Run with:
  uv run python -m uvicorn web_app:app --reload --port 8080
"""
import os
import re
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ── config ────────────────────────────────────────────────────────────
USE_AGENTCORE = os.environ.get("USE_AGENTCORE", "false").lower() == "true"

AGENTCORE_RUNTIME_URL = (
    "https://bedrock-agentcore.us-east-1.amazonaws.com"
    "/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A800881206773%3Aruntime%2FIpponAWSAssistant_ippon_assistant-D1SGcJ7zxc/invocations"
)

# ── thinking tag filter ───────────────────────────────────────────────
_THINKING_RE = re.compile(r'<thinking>.*?</thinking>', re.DOTALL)

def _strip_thinking(text: str) -> str:
    """Remove <thinking>...</thinking> blocks from model output."""
    return _THINKING_RE.sub('', text).lstrip('\n')

# ── app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Ippon Assistant - AWS Cost Estimator")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=(STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# ── AgentCore invocation ──────────────────────────────────────────────

async def _stream_agentcore(prompt: str):
    """Invoke AgentCore Runtime and stream the response chunks."""
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    region = session.region_name or "us-east-1"

    payload = json.dumps({"prompt": prompt}).encode()

    request = AWSRequest(
        method="POST",
        url=AGENTCORE_RUNTIME_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials, "bedrock-agentcore", region).add_auth(request)
    signed_headers = dict(request.headers)

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
                # AgentCore streams JSON-encoded strings e.g. "hello" or {"data":"hello"}
                # Try to decode JSON, fallback to raw text
                chunk = chunk.strip()
                try:
                    decoded = json.loads(chunk)
                    if isinstance(decoded, str):
                        yield decoded
                    elif isinstance(decoded, dict):
                        yield decoded.get("data", decoded.get("text", str(decoded)))
                    else:
                        yield str(decoded)
                except (json.JSONDecodeError, ValueError):
                    yield chunk


# ── local agent invocation ────────────────────────────────────────────

async def _stream_local(prompt: str):
    """Invoke the local Strands agent."""
    from agent import get_or_create_agent
    agent = get_or_create_agent()
    async for event in agent.stream_async(prompt):
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


# ── /chat endpoint ────────────────────────────────────────────────────

@app.post("/chat")
async def chat(
    message: str = Form(...),
    spec_file: UploadFile | None = File(default=None),
):
    prompt = message

    if spec_file and spec_file.filename:
        spec_text = (await spec_file.read()).decode("utf-8", errors="replace")
        prompt = (
            f"Here is the infrastructure spec file ({spec_file.filename}):\n\n"
            f"```\n{spec_text}\n```\n\n"
            f"User request: {message}"
        )

    async def event_stream():
        accumulated = ""
        try:
            stream = _stream_agentcore(prompt) if USE_AGENTCORE else _stream_local(prompt)
            async for chunk in stream:
                accumulated += chunk
                # Strip thinking tags from accumulated buffer
                clean = _strip_thinking(accumulated)
                if clean:
                    # Send only the new clean content
                    to_send = clean.replace("\n", "\\n")
                    yield f"data: {to_send}\n\n"
                    accumulated = ""
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            # Flush any remaining content
            if accumulated:
                clean = _strip_thinking(accumulated)
                if clean:
                    yield f"data: {clean.replace(chr(10), chr(92) + 'n')}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/mode")
async def mode():
    return {
        "mode": "agentcore" if USE_AGENTCORE else "local",
        "runtime_url": AGENTCORE_RUNTIME_URL if USE_AGENTCORE else None,
    }
