from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent import get_or_create_agent

app = BedrockAgentCoreApp()
log = app.logger


@app.entrypoint
async def invoke(payload, context):
    log.info("Invoking Agent.....")
    agent = get_or_create_agent()

    async for event in agent.stream_async(payload.get("prompt")):
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
