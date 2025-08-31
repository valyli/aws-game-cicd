#!/bin/bash
# One-click deployment script for Jenkins Unity CI/CD

set -e

# Default parameters
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"
CONFIG_FILE="${CONFIG_FILE:-default}"

echo "Deploying Jenkins Unity CI/CD with following configuration:"
echo "  Project Prefix: $PROJECT_PREFIX"
echo "  AWS Region: $AWS_REGION"
echo "  Unity Version: $UNITY_VERSION"
echo "  Config File: $CONFIG_FILE"

# Check dependencies
command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required"; exit 1; }
command -v cdk >/dev/null 2>&1 || { echo "AWS CDK is required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required"; exit 1; }

# Get AWS account information
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "  AWS Account: $AWS_ACCOUNT_ID"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Bootstrap CDK if needed
echo "Checking CDK bootstrap..."
cdk bootstrap aws://$AWS_ACCOUNT_ID/$AWS_REGION

# Deploy CDK stack
echo "Deploying CDK stack..."
cdk deploy \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  -c config_file="$CONFIG_FILE" \
  --require-approval never

echo "Deployment completed successfully!"
echo "VPC and network infrastructure has been created."
echo "Next steps:"
echo "  1. Verify VPC and subnets in AWS Console"
echo "  2. Continue with storage stack deployment"