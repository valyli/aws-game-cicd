#!/bin/bash
# One-click Unity Agent Setup
set -e

echo "=========================================="
echo "    Unity Agent AMI Setup & Deployment"
echo "=========================================="
echo ""

# Configuration
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"

echo "Configuration:"
echo "  Project Prefix: $PROJECT_PREFIX"
echo "  AWS Region: $AWS_REGION"
echo "  Unity Version: $UNITY_VERSION"
echo ""

# Step 1: Build Unity Agent AMI
echo "Step 1/3: Building Unity Agent AMI..."
echo "This will take 30-60 minutes..."
./build-unity-agent-ami.sh

# Step 2: Update Jenkins Agent Stack
echo ""
echo "Step 2/3: Updating Jenkins Agent Stack..."
./update-agent-ami.sh

# Step 3: Deploy updated infrastructure
echo ""
echo "Step 3/3: Deploying updated infrastructure..."
echo "This will update your Jenkins Agent instances to use Unity AMI..."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Install CDK dependencies if needed
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# Deploy only the Jenkins Agent Stack
echo "Deploying Jenkins Agent Stack with Unity AMI..."
cdk deploy unity-cicd-jenkins-agent-stack \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  --require-approval never || {
    echo "Jenkins Agent Stack deployment failed. Check the error above."
    exit 1
  }

echo ""
echo "=========================================="
echo "           SETUP COMPLETED!"
echo "=========================================="
echo ""
echo "Unity Agent AMI has been created and deployed successfully!"
echo ""
echo "What was done:"
echo "1. ✅ Built Unity Agent AMI with Unity $UNITY_VERSION pre-installed"
echo "2. ✅ Updated Jenkins Agent Stack to use the new AMI"
echo "3. ✅ Deployed the updated infrastructure"
echo ""
echo "Your Jenkins Agents now have Unity pre-installed and will start much faster!"
echo ""
echo "AMI Details:"
cat config/amis.yaml
echo ""
echo "Next steps:"
echo "- Your Jenkins Agents will now launch with Unity pre-installed"
echo "- Build times will be significantly faster"
echo "- No more waiting for Unity installation during agent startup"