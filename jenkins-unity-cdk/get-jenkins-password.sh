#!/bin/bash

# Get Jenkins Master instance ID
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
    --auto-scaling-group-names unity-cicd-jenkins-master-asg \
    --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
    --output text)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
    echo "❌ No Jenkins instance found in ASG"
    exit 1
fi

echo "🔍 Jenkins instance: $INSTANCE_ID"

# Get Jenkins initial password via SSM
COMMAND_ID=$(aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["cat /var/lib/jenkins/.jenkins/secrets/initialAdminPassword 2>/dev/null || echo PASSWORD_NOT_FOUND"]' \
    --query 'Command.CommandId' \
    --output text)

echo "⏳ Getting password..."
sleep 5

PASSWORD=$(aws ssm get-command-invocation \
    --command-id $COMMAND_ID \
    --instance-id $INSTANCE_ID \
    --query 'StandardOutputContent' \
    --output text | tr -d '\n')

if [ "$PASSWORD" = "PASSWORD_NOT_FOUND" ] || [ -z "$PASSWORD" ]; then
    echo "❌ Jenkins password not found. Jenkins may still be starting up."
    echo "💡 Try again in a few minutes or check the user-data log:"
    echo "   aws ssm send-command --instance-ids $INSTANCE_ID --document-name 'AWS-RunShellScript' --parameters 'commands=[\"tail -50 /var/log/user-data.log\"]'"
    exit 1
fi

echo ""
echo "🔐 Jenkins Initial Admin Password:"
echo "=================================="
echo "$PASSWORD"
echo "=================================="
echo ""
echo "🌐 Jenkins URL: http://unity-cicd-jenkins-alb-1860412095.us-east-1.elb.amazonaws.com:8080"
echo ""