#!/bin/bash
# Deploy the AWS Pricing Lambda function
# Usage: ./deploy.sh [REGION] [ACCOUNT_ID]

REGION=${1:-us-east-1}
ACCOUNT_ID=${2:-$(aws sts get-caller-identity --query Account --output text)}
FUNCTION_NAME="aws-pricing-mcp"
ROLE_NAME="aws-pricing-mcp-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

echo "==> Creating IAM role..."
aws iam create-role \
  --role-name $ROLE_NAME \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Principal":{"Service":"lambda.amazonaws.com"},
      "Action":"sts:AssumeRole"
    }]
  }' --region $REGION 2>/dev/null || echo "Role already exists"

echo "==> Attaching policies..."
aws iam attach-role-policy \
  --role-name $ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam attach-role-policy \
  --role-name $ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/AWSPriceListServiceFullAccess

echo "==> Waiting for role propagation..."
sleep 10

echo "==> Packaging Lambda..."
zip -j pricing_lambda.zip lambda_function.py

echo "==> Deploying Lambda..."
aws lambda create-function \
  --function-name $FUNCTION_NAME \
  --runtime python3.12 \
  --role $ROLE_ARN \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://pricing_lambda.zip \
  --timeout 30 \
  --region $REGION 2>/dev/null || \
aws lambda update-function-code \
  --function-name $FUNCTION_NAME \
  --zip-file fileb://pricing_lambda.zip \
  --region $REGION

echo "==> Getting Lambda ARN..."
LAMBDA_ARN=$(aws lambda get-function \
  --function-name $FUNCTION_NAME \
  --region $REGION \
  --query 'Configuration.FunctionArn' \
  --output text)

echo ""
echo "✅ Lambda deployed!"
echo "   ARN: $LAMBDA_ARN"
echo ""
echo "Next step — add as Gateway target:"
echo "  GATEWAY_ARN=<your-gateway-arn>"
echo "  GATEWAY_URL=https://gateway-quick-start-0648dc-gpysmooxhe.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
echo "  ROLE_ARN=<gateway-execution-role-arn>"
echo ""
echo "  agentcore gateway create-mcp-gateway-target \\"
echo "    --gateway-arn \$GATEWAY_ARN \\"
echo "    --gateway-url \$GATEWAY_URL \\"
echo "    --role-arn \$ROLE_ARN \\"
echo "    --name PricingTarget \\"
echo "    --target-type lambda \\"
echo "    --target-payload \"\$(cat gateway_target.json)\" \\"
echo "    --region $REGION"

rm -f pricing_lambda.zip
