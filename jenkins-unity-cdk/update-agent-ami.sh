#!/bin/bash
# Update Jenkins Agent Stack to use Unity AMI
set -e

echo "=== Updating Jenkins Agent Stack to use Unity AMI ==="

# Check if AMI config exists
if [ ! -f "config/amis.yaml" ]; then
    echo "ERROR: config/amis.yaml not found. Please run build-unity-agent-ami.sh first."
    exit 1
fi

# Extract AMI ID from config
UNITY_AGENT_AMI=$(grep "unity_agent:" config/amis.yaml | cut -d'"' -f2)
AWS_REGION=$(grep "aws_region:" config/amis.yaml | cut -d'"' -f2)

if [ -z "$UNITY_AGENT_AMI" ]; then
    echo "ERROR: Could not find Unity Agent AMI ID in config/amis.yaml"
    exit 1
fi

echo "Unity Agent AMI: $UNITY_AGENT_AMI"
echo "AWS Region: $AWS_REGION"

# Backup original file
cp stacks/jenkins_agent_stack.py stacks/jenkins_agent_stack.py.backup
echo "Backup created: stacks/jenkins_agent_stack.py.backup"

# Update the Jenkins Agent Stack to use the Unity AMI
python3 << EOF
import re

# Read the file
with open('stacks/jenkins_agent_stack.py', 'r') as f:
    content = f.read()

# Replace the machine_image line
old_pattern = r'machine_image=ec2\.MachineImage\.latest_amazon_linux2023\(\)'
new_line = f"machine_image=ec2.MachineImage.generic_linux({{'$AWS_REGION': '$UNITY_AGENT_AMI'}})"

if old_pattern in content:
    content = re.sub(old_pattern, new_line, content)
    print("Updated machine_image to use Unity Agent AMI")
else:
    print("WARNING: Could not find the expected machine_image pattern")
    print("Please manually update the machine_image in jenkins_agent_stack.py")

# Write back the file
with open('stacks/jenkins_agent_stack.py', 'w') as f:
    f.write(content)
EOF

echo "Jenkins Agent Stack updated successfully"
echo ""
echo "Changes made:"
echo "  - Updated machine_image to use Unity Agent AMI: $UNITY_AGENT_AMI"
echo "  - Backup saved as: stacks/jenkins_agent_stack.py.backup"
echo ""
echo "Next steps:"
echo "1. Review the changes in stacks/jenkins_agent_stack.py"
echo "2. Deploy the updated stack: cdk deploy"
echo ""
echo "To revert changes: mv stacks/jenkins_agent_stack.py.backup stacks/jenkins_agent_stack.py"