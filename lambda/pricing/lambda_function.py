"""
AWS Pricing Lambda — exposed as MCP tool via AgentCore Gateway.

Tools exposed:
  - get_pricing        : query pricing for a specific service/filters
  - list_services      : list all AWS services available in Pricing API
  - get_attribute_values : list valid values for a pricing attribute
"""
import json
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

pricing_client = boto3.client("pricing", region_name="us-east-1")


# ── tool implementations ──────────────────────────────────────────────

def list_services() -> dict:
    """List all AWS services available in the Pricing API."""
    paginator = pricing_client.get_paginator("describe_services")
    services = []
    for page in paginator.paginate():
        for svc in page["Services"]:
            services.append({
                "serviceCode": svc["ServiceCode"],
                "attributeNames": svc.get("AttributeNames", [])
            })
    return {"services": services, "count": len(services)}


def get_attribute_values(service_code: str, attribute_name: str) -> dict:
    """Get valid values for a pricing attribute of a given service."""
    paginator = pricing_client.get_paginator("get_attribute_values")
    values = []
    for page in paginator.paginate(
        ServiceCode=service_code,
        AttributeName=attribute_name
    ):
        for v in page["AttributeValues"]:
            values.append(v["Value"])
    return {"serviceCode": service_code, "attribute": attribute_name, "values": values}


def get_pricing(service_code: str, filters: list, max_results: int = 10) -> dict:
    """
    Query AWS pricing for a service with filters.

    filters format:
      [{"Field": "instanceType", "Value": "t3.medium"},
       {"Field": "location",     "Value": "US East (N. Virginia)"},
       {"Field": "operatingSystem", "Value": "Linux"},
       {"Field": "tenancy",     "Value": "Shared"},
       {"Field": "preInstalledSw", "Value": "NA"},
       {"Field": "capacitystatus", "Value": "Used"}]
    """
    boto_filters = [
        {"Type": "TERM_MATCH", "Field": f["Field"], "Value": f["Value"]}
        for f in filters
    ]

    response = pricing_client.get_products(
        ServiceCode=service_code,
        Filters=boto_filters,
        MaxResults=min(max_results, 100),
        FormatVersion="aws_v1"
    )

    results = []
    for price_item_str in response.get("PriceList", []):
        price_item = json.loads(price_item_str)
        product    = price_item.get("product", {})
        attributes = product.get("attributes", {})
        terms      = price_item.get("terms", {})

        # Extract on-demand price
        on_demand = terms.get("OnDemand", {})
        prices = []
        for offer in on_demand.values():
            for dim in offer.get("priceDimensions", {}).values():
                usd = dim.get("pricePerUnit", {}).get("USD", "0")
                prices.append({
                    "description": dim.get("description", ""),
                    "unit":        dim.get("unit", ""),
                    "priceUSD":    float(usd),
                })

        results.append({
            "serviceCode": service_code,
            "attributes": attributes,
            "onDemandPrices": prices,
        })

    return {
        "serviceCode": service_code,
        "filters": filters,
        "count": len(results),
        "results": results,
    }


# ── tool registry ─────────────────────────────────────────────────────

TOOLS = {
    "list_services": {
        "description": "List all AWS services available in the Pricing API",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "get_attribute_values": {
        "description": "Get valid attribute values for a given AWS service (e.g. instanceType for AmazonEC2)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_code": {"type": "string", "description": "AWS service code e.g. AmazonEC2, AmazonRDS"},
                "attribute_name": {"type": "string", "description": "Attribute name e.g. instanceType, location"}
            },
            "required": ["service_code", "attribute_name"]
        }
    },
    "get_pricing": {
        "description": "Get real-time AWS pricing for a service with filters. Returns on-demand prices.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_code": {
                    "type": "string",
                    "description": "AWS service code e.g. AmazonEC2, AmazonRDS, AmazonS3"
                },
                "filters": {
                    "type": "array",
                    "description": "List of {Field, Value} filter objects",
                    "items": {
                        "type": "object",
                        "properties": {
                            "Field": {"type": "string"},
                            "Value": {"type": "string"}
                        }
                    }
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max number of results to return (default 10)",
                    "default": 10
                }
            },
            "required": ["service_code", "filters"]
        }
    }
}


# ── MCP protocol handler ──────────────────────────────────────────────

def handle_mcp_request(body: dict) -> dict:
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id", 1)

    # tools/list
    if method == "tools/list":
        tools_list = [
            {"name": name, "description": meta["description"], "inputSchema": meta["inputSchema"]}
            for name, meta in TOOLS.items()
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}

    # tools/call
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "list_services":
                result = list_services()
            elif tool_name == "get_attribute_values":
                result = get_attribute_values(
                    arguments["service_code"],
                    arguments["attribute_name"]
                )
            elif tool_name == "get_pricing":
                result = get_pricing(
                    arguments["service_code"],
                    arguments.get("filters", []),
                    arguments.get("max_results", 10)
                )
            else:
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                }

            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": False
                }
            }

        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True
                }
            }

    # initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "aws-pricing-lambda", "version": "1.0.0"}
            }
        }

    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    }


# ── Lambda entrypoint ─────────────────────────────────────────────────

def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")

    try:
        # Gateway sends arguments directly (flat dict) — not JSON-RPC
        # Detect by checking if it looks like a direct tool call
        if "method" not in event and isinstance(event.get("body"), str):
            # API Gateway with body string
            body = json.loads(event["body"])
        elif "method" in event:
            # JSON-RPC format
            body = event
        else:
            # Direct invocation from AgentCore Gateway — flat arguments
            # Determine which tool was called based on the arguments present
            if "service_code" in event and "filters" in event:
                tool_name = "get_pricing"
            elif "service_code" in event and "attribute_name" in event:
                tool_name = "get_attribute_values"
            else:
                tool_name = "list_services"

            # Wrap as JSON-RPC tools/call
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": event
                }
            }

        response_body = handle_mcp_request(body)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(response_body)
        }

    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
