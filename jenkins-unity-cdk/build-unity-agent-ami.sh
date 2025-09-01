#!/bin/bash
# Automated Unity Agent AMI Builder
set -e

echo "=== Unity Agent AMI Builder ==="
echo "Starting automated build process..."

# Configuration
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"
ANDROID_SDK_VERSION="${ANDROID_SDK_VERSION:-34}"

echo "Configuration:"
echo "  Project Prefix: $PROJECT_PREFIX"
echo "  AWS Region: $AWS_REGION"
echo "  Unity Version: $UNITY_VERSION"
echo "  Android SDK Version: $ANDROID_SDK_VERSION"

# Check prerequisites
echo "Checking prerequisites..."
command -v aws >/dev/null 2>&1 || { echo "ERROR: AWS CLI is required"; exit 1; }

# Get AWS account info
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "  AWS Account: $AWS_ACCOUNT_ID"

# Install Packer if not present
if ! command -v packer >/dev/null 2>&1; then
    echo "Installing Packer via direct download..."
    
    PACKER_VERSION="1.9.4"
    echo "Downloading Packer ${PACKER_VERSION}..."
    
    # Use temporary directory to avoid conflicts
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Download and install Packer
    wget -q "https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip" || {
        echo "ERROR: Failed to download Packer"
        exit 1
    }
    
    unzip -q "packer_${PACKER_VERSION}_linux_amd64.zip" || {
        echo "ERROR: Failed to extract Packer"
        exit 1
    }
    
    sudo mv packer /usr/local/bin/packer || {
        echo "ERROR: Failed to install Packer to /usr/local/bin/"
        exit 1
    }
    
    # Return to original directory and cleanup
    cd - > /dev/null
    rm -rf "$TEMP_DIR"
    echo "Packer installed successfully"
else
    echo "Packer already installed: $(packer version)"
fi

# Verify Packer installation
packer version || { echo "ERROR: Packer installation failed"; exit 1; }

# Initialize Packer plugins
echo "Initializing Packer plugins..."
cd packer
packer init unity-agent.pkr.hcl

# Build Unity Agent AMI
echo "Building Unity Agent AMI..."
echo "This may take 30-60 minutes depending on download speeds..."

packer build \
  -var "project_prefix=$PROJECT_PREFIX" \
  -var "aws_region=$AWS_REGION" \
  -var "unity_version=$UNITY_VERSION" \
  -var "android_sdk_version=$ANDROID_SDK_VERSION" \
  unity-agent.pkr.hcl

# Get the newly created AMI ID
echo "Retrieving AMI information..."
UNITY_AGENT_AMI=$(aws ec2 describe-images \
  --owners $AWS_ACCOUNT_ID \
  --filters "Name=name,Values=$PROJECT_PREFIX-unity-agent-*" "Name=state,Values=available" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text \
  --region $AWS_REGION)

if [ "$UNITY_AGENT_AMI" = "None" ] || [ -z "$UNITY_AGENT_AMI" ]; then
    echo "ERROR: Failed to find the created AMI"
    exit 1
fi

echo "Unity Agent AMI created successfully: $UNITY_AGENT_AMI"

# Create AMI configuration file
cd ..
mkdir -p config
cat > config/amis.yaml << EOF
# AMI IDs for Jenkins Unity CI/CD
amis:
  unity_agent: "$UNITY_AGENT_AMI"
  
# Build information
build_info:
  build_date: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  unity_version: "$UNITY_VERSION"
  android_sdk_version: "$ANDROID_SDK_VERSION"
  aws_region: "$AWS_REGION"
  aws_account: "$AWS_ACCOUNT_ID"
  project_prefix: "$PROJECT_PREFIX"
EOF

echo "AMI configuration saved to config/amis.yaml"

# Display summary
echo ""
echo "=== BUILD COMPLETED SUCCESSFULLY ==="
echo "Unity Agent AMI: $UNITY_AGENT_AMI"
echo "Configuration file: config/amis.yaml"
echo ""
echo "Next steps:"
echo "1. Update Jenkins Agent Stack to use the new AMI"
echo "2. Redeploy the infrastructure"
echo ""
echo "To use this AMI in your Jenkins Agent Stack, update the machine_image in jenkins_agent_stack.py:"
echo "  machine_image=ec2.MachineImage.generic_linux({'$AWS_REGION': '$UNITY_AGENT_AMI'})"