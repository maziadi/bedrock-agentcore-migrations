#!/bin/bash
# Build Lambda deployment package locally (no Docker needed)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$SCRIPT_DIR/lambda_package"

echo "==> Cleaning previous build..."
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

echo "==> Installing dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements_lambda.txt" -t "$PACKAGE_DIR" --quiet

echo "==> Copying app files..."
cp "$SCRIPT_DIR/web_app_lambda.py" "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/web_app.py"        "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/agent.py"          "$PACKAGE_DIR/"
cp -r "$SCRIPT_DIR/model"          "$PACKAGE_DIR/"
cp -r "$SCRIPT_DIR/mcp_client"     "$PACKAGE_DIR/"
cp -r "$SCRIPT_DIR/static"         "$PACKAGE_DIR/"

echo "==> Done! Package ready at: $PACKAGE_DIR"
echo "    You can now run: cd p1/infra/cdk && npx cdk deploy"
