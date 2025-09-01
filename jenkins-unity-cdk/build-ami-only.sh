#!/bin/bash
# Build Unity Agent AMI Only (No Deployment)
set -e

echo "=== Building Unity Agent AMI ==="

# Configuration
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"
ANDROID_SDK_VERSION="${ANDROID_SDK_VERSION:-34}"

echo "Configuration:"
echo "  Project Prefix: $PROJECT_PREFIX"
echo "  AWS Region: $AWS_REGION"
echo "  Unity Version: $UNITY_VERSION"

# Check AWS CLI
command -v aws >/dev/null 2>&1 || { echo "ERROR: AWS CLI required"; exit 1; }

# Get AWS account
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "  AWS Account: $AWS_ACCOUNT_ID"

# Install Packer if needed
if ! command -v packer >/dev/null 2>&1; then
    echo "Installing Packer..."
    PACKER_VERSION="1.9.4"
    wget -q "https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip"
    unzip -q "packer_${PACKER_VERSION}_linux_amd64.zip"
    sudo mv packer /usr/local/bin/
    rm "packer_${PACKER_VERSION}_linux_amd64.zip"
    echo "Packer installed"
fi

# Verify Packer
packer version

# Initialize and build
echo "Building AMI (this takes 30-60 minutes)..."
cd packer
packer init unity-agent.pkr.hcl
packer build \
  -var "project_prefix=$PROJECT_PREFIX" \
  -var "aws_region=$AWS_REGION" \
  -var "unity_version=$UNITY_VERSION" \
  -var "android_sdk_version=$ANDROID_SDK_VERSION" \
  unity-agent.pkr.hcl

# Get AMI ID
cd ..
UNITY_AGENT_AMI=$(aws ec2 describe-images \
  --owners $AWS_ACCOUNT_ID \
  --filters "Name=name,Values=$PROJECT_PREFIX-unity-agent-*" "Name=state,Values=available" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text \
  --region $AWS_REGION)

# Save config
mkdir -p config
cat > config/amis.yaml << EOF
amis:
  unity_agent: "$UNITY_AGENT_AMI"
build_info:
  build_date: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  unity_version: "$UNITY_VERSION"
  aws_region: "$AWS_REGION"
  aws_account: "$AWS_ACCOUNT_ID"
EOF

echo ""
echo "=== AMI BUILD COMPLETED ==="
echo "Unity Agent AMI: $UNITY_AGENT_AMI"
echo "Config saved to: config/amis.yaml"
echo ""
echo "Next: Run ./update-agent-ami.sh to update your Jenkins Agent Stack"