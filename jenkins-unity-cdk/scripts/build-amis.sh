#!/bin/bash
# Build AMIs for Jenkins Unity CI/CD

set -e

# Default parameters
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"
JENKINS_VERSION="${JENKINS_VERSION:-2.426.1}"
ANDROID_SDK_VERSION="${ANDROID_SDK_VERSION:-34}"

echo "Building AMIs for Jenkins Unity CI/CD with following configuration:"
echo "  Project Prefix: $PROJECT_PREFIX"
echo "  AWS Region: $AWS_REGION"
echo "  Unity Version: $UNITY_VERSION"
echo "  Jenkins Version: $JENKINS_VERSION"
echo "  Android SDK Version: $ANDROID_SDK_VERSION"

# Check dependencies
command -v packer >/dev/null 2>&1 || { echo "Packer is required"; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required"; exit 1; }

# Get AWS account information
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "  AWS Account: $AWS_ACCOUNT_ID"

# Change to packer directory
cd "$(dirname "$0")/../packer"

# Build Jenkins Master AMI
echo "Building Jenkins Master AMI..."
packer build \
  -var "project_prefix=$PROJECT_PREFIX" \
  -var "aws_region=$AWS_REGION" \
  -var "jenkins_version=$JENKINS_VERSION" \
  jenkins-master.pkr.hcl

# Get the Jenkins Master AMI ID
JENKINS_MASTER_AMI=$(aws ec2 describe-images \
  --owners $AWS_ACCOUNT_ID \
  --filters "Name=name,Values=$PROJECT_PREFIX-jenkins-master-*" "Name=state,Values=available" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text \
  --region $AWS_REGION)

echo "Jenkins Master AMI: $JENKINS_MASTER_AMI"

# Build Unity Agent AMI
echo "Building Unity Agent AMI..."
packer build \
  -var "project_prefix=$PROJECT_PREFIX" \
  -var "aws_region=$AWS_REGION" \
  -var "unity_version=$UNITY_VERSION" \
  -var "android_sdk_version=$ANDROID_SDK_VERSION" \
  unity-agent.pkr.hcl

# Get the Unity Agent AMI ID
UNITY_AGENT_AMI=$(aws ec2 describe-images \
  --owners $AWS_ACCOUNT_ID \
  --filters "Name=name,Values=$PROJECT_PREFIX-unity-agent-*" "Name=state,Values=available" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text \
  --region $AWS_REGION)

echo "Unity Agent AMI: $UNITY_AGENT_AMI"

# Create AMI configuration file for CDK
cat > ../config/amis.yaml << EOF
# AMI IDs for Jenkins Unity CI/CD
amis:
  jenkins_master: "$JENKINS_MASTER_AMI"
  unity_agent: "$UNITY_AGENT_AMI"
  
# Build information
build_info:
  build_date: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  unity_version: "$UNITY_VERSION"
  jenkins_version: "$JENKINS_VERSION"
  android_sdk_version: "$ANDROID_SDK_VERSION"
  aws_region: "$AWS_REGION"
  aws_account: "$AWS_ACCOUNT_ID"
EOF

echo "AMI build completed successfully!"
echo "AMI configuration saved to config/amis.yaml"
echo ""
echo "Next steps:"
echo "  1. Update your CDK configuration to use the new AMIs"
echo "  2. Deploy the updated infrastructure"
echo ""
echo "Jenkins Master AMI: $JENKINS_MASTER_AMI"
echo "Unity Agent AMI: $UNITY_AGENT_AMI"