#!/bin/bash
# Complete deployment script for Jenkins Unity CI/CD

set -e

# Default parameters
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"
CONFIG_FILE="${CONFIG_FILE:-default}"
ENVIRONMENT="${ENVIRONMENT:-development}"

echo "=========================================="
echo "Jenkins Unity CI/CD Complete Deployment"
echo "=========================================="
echo "  Project Prefix: $PROJECT_PREFIX"
echo "  AWS Region: $AWS_REGION"
echo "  Unity Version: $UNITY_VERSION"
echo "  Config File: $CONFIG_FILE"
echo "  Environment: $ENVIRONMENT"
echo "=========================================="

# Check dependencies
command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required"; exit 1; }
command -v cdk >/dev/null 2>&1 || { echo "AWS CDK is required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required"; exit 1; }

# Get AWS account information
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account: $AWS_ACCOUNT_ID"

# Change to project directory
cd "$(dirname "$0")/.."

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

# Deploy infrastructure in stages
echo "=========================================="
echo "Stage 1: Core Infrastructure (VPC, Storage, IAM)"
echo "=========================================="

cdk deploy \
  ${PROJECT_PREFIX}-vpc-stack \
  ${PROJECT_PREFIX}-storage-stack \
  ${PROJECT_PREFIX}-iam-stack \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  -c config_file="$CONFIG_FILE" \
  -c environment="$ENVIRONMENT" \
  --require-approval never

echo "Core infrastructure deployed successfully!"

echo "=========================================="
echo "Stage 2: Lambda Functions"
echo "=========================================="

cdk deploy \
  ${PROJECT_PREFIX}-lambda-stack \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  -c config_file="$CONFIG_FILE" \
  -c environment="$ENVIRONMENT" \
  --require-approval never

echo "Lambda functions deployed successfully!"

echo "=========================================="
echo "Stage 3: Jenkins Master"
echo "=========================================="

cdk deploy \
  ${PROJECT_PREFIX}-jenkins-master-stack \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  -c config_file="$CONFIG_FILE" \
  -c environment="$ENVIRONMENT" \
  --require-approval never

echo "Jenkins Master deployed successfully!"

# Wait for Jenkins Master to be ready
echo "Waiting for Jenkins Master to be ready..."
JENKINS_URL=$(aws cloudformation describe-stacks \
  --stack-name ${PROJECT_PREFIX}-jenkins-master-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
  --output text \
  --region $AWS_REGION)

echo "Jenkins URL: $JENKINS_URL"

# Wait for Jenkins to be accessible
echo "Waiting for Jenkins to be accessible..."
for i in {1..30}; do
  if curl -s -o /dev/null -w "%{http_code}" "$JENKINS_URL" | grep -q "200\|403"; then
    echo "Jenkins is accessible!"
    break
  fi
  echo "Attempt $i/30: Jenkins not ready yet, waiting 30 seconds..."
  sleep 30
done

echo "=========================================="
echo "Stage 4: Jenkins Agents"
echo "=========================================="

cdk deploy \
  ${PROJECT_PREFIX}-jenkins-agent-stack \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  -c config_file="$CONFIG_FILE" \
  -c environment="$ENVIRONMENT" \
  --require-approval never

echo "Jenkins Agents deployed successfully!"

echo "=========================================="
echo "Stage 5: Monitoring"
echo "=========================================="

cdk deploy \
  ${PROJECT_PREFIX}-monitoring-stack \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  -c config_file="$CONFIG_FILE" \
  -c environment="$ENVIRONMENT" \
  --require-approval never

echo "Monitoring deployed successfully!"

echo "=========================================="
echo "Deployment Summary"
echo "=========================================="

# Get deployment outputs
VPC_ID=$(aws cloudformation describe-stacks \
  --stack-name ${PROJECT_PREFIX}-vpc-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`VpcId`].OutputValue' \
  --output text \
  --region $AWS_REGION)

EFS_ID=$(aws cloudformation describe-stacks \
  --stack-name ${PROJECT_PREFIX}-storage-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`JenkinsEFSId`].OutputValue' \
  --output text \
  --region $AWS_REGION)

CACHE_TABLE=$(aws cloudformation describe-stacks \
  --stack-name ${PROJECT_PREFIX}-storage-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`CachePoolTableName`].OutputValue' \
  --output text \
  --region $AWS_REGION)

ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name ${PROJECT_PREFIX}-jenkins-master-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`JenkinsALBDNSName`].OutputValue' \
  --output text \
  --region $AWS_REGION)

DASHBOARD_URL=$(aws cloudformation describe-stacks \
  --stack-name ${PROJECT_PREFIX}-monitoring-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
  --output text \
  --region $AWS_REGION 2>/dev/null || echo "Not available")

ALERTS_TOPIC=$(aws cloudformation describe-stacks \
  --stack-name ${PROJECT_PREFIX}-monitoring-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`AlertsTopicArn`].OutputValue' \
  --output text \
  --region $AWS_REGION 2>/dev/null || echo "Not available")

echo "Infrastructure Details:"
echo "  VPC ID: $VPC_ID"
echo "  EFS ID: $EFS_ID"
echo "  Cache Pool Table: $CACHE_TABLE"
echo ""
echo "Jenkins Access:"
echo "  Jenkins URL: $JENKINS_URL"
echo "  ALB DNS: $ALB_DNS"
echo "  Default Credentials: admin/admin123"
echo ""
echo "Monitoring:"
echo "  Dashboard: $DASHBOARD_URL"
echo "  Alerts Topic: $ALERTS_TOPIC"
echo ""
echo "Next Steps:"
echo "  1. Access Jenkins at: $JENKINS_URL"
echo "  2. Configure Unity license in Systems Manager Parameter Store:"
echo "     - /jenkins/unity/username"
echo "     - /jenkins/unity/password"
echo "     - /jenkins/unity/serial"
echo "  3. Subscribe to alerts topic for notifications"
echo "  4. Build custom AMIs using: ./scripts/build-amis.sh"
echo "  5. Update Jenkins cloud configuration with new AMI IDs"
echo ""
echo "=========================================="
echo "Deployment completed successfully!"
echo "=========================================="