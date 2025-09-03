#!/bin/bash
# Linux Jenkins JNLP Agent Auto-Connect Script
exec > >(tee /var/log/jenkins-agent-setup.log) 2>&1

echo "=== Starting Linux Jenkins Agent Setup ==="
echo "Time: $(date)"

# Get instance metadata with retry
echo "=== Getting Instance Metadata ==="
for i in {1..5}; do
    INSTANCE_ID=$(curl -s --max-time 10 http://169.254.169.254/latest/meta-data/instance-id)
    if [ ! -z "$INSTANCE_ID" ]; then
        echo "Got Instance ID: $INSTANCE_ID"
        break
    fi
    echo "Retry $i/5: Getting instance ID..."
    sleep 5
done

PRIVATE_IP=$(curl -s --max-time 10 http://169.254.169.254/latest/meta-data/local-ipv4)
REGION=$(curl -s --max-time 10 http://169.254.169.254/latest/meta-data/placement/region)

# Fallback if metadata fails
if [ -z "$INSTANCE_ID" ]; then
    INSTANCE_ID=$(ec2-metadata --instance-id 2>/dev/null | cut -d' ' -f2 || hostname)
    echo "Using fallback Instance ID: $INSTANCE_ID"
fi

# Export variables to ensure they persist
export INSTANCE_ID
export PRIVATE_IP
export REGION

echo "Instance ID: $INSTANCE_ID"
echo "Private IP: $PRIVATE_IP"
echo "Region: $REGION"

# Jenkins Master configuration
JENKINS_MASTER_IP="10.0.0.154"
JENKINS_URL="http://$JENKINS_MASTER_IP:8080"
JENKINS_USER="valyli"
JENKINS_TOKEN="11e60bc68521d47c1f32944d4045590e25"
AGENT_NAME="linux-agent-${INSTANCE_ID}"
WORK_DIR="/opt/jenkins"

# Export Jenkins variables
export JENKINS_URL JENKINS_USER JENKINS_TOKEN AGENT_NAME WORK_DIR

echo "Jenkins URL: $JENKINS_URL"
echo "Agent Name: $AGENT_NAME"

# Update system and install dependencies
yum update -y
yum install -y java-17-amazon-corretto curl wget

# Verify Java installation
java -version
if [ $? -ne 0 ]; then
    echo "ERROR: Java installation failed!"
    exit 1
fi

# Create work directory
mkdir -p $WORK_DIR
cd $WORK_DIR

# Wait for Jenkins Master to be available
echo "=== Waiting for Jenkins Master ==="
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" "$JENKINS_URL/login" | grep -q "200\|403"; then
        echo "Jenkins Master is ready"
        break
    fi
    echo "Attempt $i/30: Jenkins not ready, waiting..."
    sleep 10
done

# Download Jenkins Agent JAR
echo "=== Downloading Jenkins Agent JAR ==="
curl -sO "$JENKINS_URL/jnlpJars/agent.jar"
if [ ! -f "agent.jar" ]; then
    echo "ERROR: Failed to download agent.jar"
    exit 1
fi

# Create Jenkins node via API
echo "=== Creating Jenkins Agent Node ==="

# Use Jenkins CLI approach - download CLI jar
curl -sO "$JENKINS_URL/jnlpJars/jenkins-cli.jar"

# Create node XML config
echo "Creating node config for: $AGENT_NAME"
cat > node-config.xml << EOF
<slave>
  <name>${AGENT_NAME}</name>
  <description>Auto-created Linux Agent for ${INSTANCE_ID}</description>
  <remoteFS>${WORK_DIR}</remoteFS>
  <numExecutors>2</numExecutors>
  <mode>NORMAL</mode>
  <retentionStrategy class="hudson.slaves.RetentionStrategy\$Always"/>
  <launcher class="hudson.slaves.JNLPLauncher">
    <workDirSettings>
      <disabled>false</disabled>
      <workDirPath>${WORK_DIR}</workDirPath>
      <internalDir>remoting</internalDir>
      <failIfWorkDirIsMissing>false</failIfWorkDirIsMissing>
    </workDirSettings>
  </launcher>
  <label>linux auto</label>
  <nodeProperties/>
</slave>
EOF

# Debug and create node using Jenkins CLI
echo "Final AGENT_NAME before CLI: $AGENT_NAME"
echo "Final INSTANCE_ID before CLI: $INSTANCE_ID"
java -jar jenkins-cli.jar -s "$JENKINS_URL" -auth "$JENKINS_USER:$JENKINS_TOKEN" create-node "${AGENT_NAME}" < node-config.xml && echo "Node created successfully" || echo "Node creation may have failed"

# Wait a bit for node creation
sleep 10

# Get JNLP secret
echo "=== Getting JNLP Connection Info ==="
for i in {1..10}; do
    JNLP_CONTENT=$(curl -s -u "$JENKINS_USER:$JENKINS_TOKEN" "$JENKINS_URL/computer/$AGENT_NAME/jenkins-agent.jnlp")
    SECRET=$(echo "$JNLP_CONTENT" | grep -oP '<argument>\K[^<]+' | head -1)
    if [ ! -z "$SECRET" ]; then
        echo "JNLP Secret obtained: $SECRET"
        break
    fi
    echo "Retry $i/10: Getting JNLP info failed, waiting..."
    sleep 10
done

if [ -z "$SECRET" ]; then
    echo "ERROR: Could not obtain JNLP secret"
    exit 1
fi

# Create systemd service for persistent connection
echo "=== Creating Jenkins Agent Service ==="
cat > /etc/systemd/system/jenkins-agent.service << EOF
[Unit]
Description=Jenkins Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$WORK_DIR
ExecStart=/usr/bin/java -jar agent.jar -url $JENKINS_URL -secret $SECRET -name $AGENT_NAME -workDir $WORK_DIR
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Start and enable the service
systemctl daemon-reload
systemctl enable jenkins-agent
systemctl start jenkins-agent

echo "=== Jenkins Agent Setup Completed ==="
echo "Service Status:"
systemctl status jenkins-agent --no-pager

echo "=== Setup Complete ==="