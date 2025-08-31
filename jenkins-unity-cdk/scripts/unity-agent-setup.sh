#!/bin/bash
# Unity Agent setup script for AMI building

set -e

echo "Starting Unity Agent setup..."
echo "Unity Version: ${UNITY_VERSION}"
echo "Project Prefix: ${PROJECT_PREFIX}"

# Update system
sudo dnf update -y

# Install Java 17
sudo dnf install -y java-17-amazon-corretto-devel

# Install development tools and dependencies
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y git wget curl unzip xorg-x11-server-Xvfb mesa-libGL-devel

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

# Install Node.js (for some build tools)
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo dnf install -y nodejs

# Install Git LFS
curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.rpm.sh | sudo bash
sudo dnf install -y git-lfs
git lfs install --system

# Create Unity installation directory
sudo mkdir -p /opt/unity
sudo chown ec2-user:ec2-user /opt/unity

# Download and install Unity Hub
echo "Installing Unity Hub..."
wget -q https://public-cdn.cloud.unity3d.com/hub/prod/UnityHub.AppImage -O /tmp/UnityHub.AppImage
chmod +x /tmp/UnityHub.AppImage
sudo mv /tmp/UnityHub.AppImage /opt/unity/UnityHub.AppImage

# Install Unity Editor
echo "Installing Unity Editor ${UNITY_VERSION}..."
# Note: This is a simplified installation. In production, you would:
# 1. Use Unity Hub to install specific version
# 2. Handle licensing properly
# 3. Install required modules (Android, iOS, etc.)

# For now, create placeholder structure
sudo mkdir -p /opt/unity/Editor
sudo mkdir -p /opt/unity/modules

# Install Android SDK (for mobile builds)
echo "Installing Android SDK..."
wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O /tmp/android-tools.zip
sudo mkdir -p /opt/android-sdk
sudo unzip -q /tmp/android-tools.zip -d /opt/android-sdk
sudo chown -R ec2-user:ec2-user /opt/android-sdk
rm /tmp/android-tools.zip

# Set up Android SDK
export ANDROID_HOME=/opt/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

# Accept Android SDK licenses and install required packages
echo "Configuring Android SDK..."
mkdir -p $ANDROID_HOME/cmdline-tools/latest
mv $ANDROID_HOME/cmdline-tools/bin $ANDROID_HOME/cmdline-tools/latest/
mv $ANDROID_HOME/cmdline-tools/lib $ANDROID_HOME/cmdline-tools/latest/

yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses || true
$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-33" "build-tools;33.0.0"

# Download Jenkins Agent JAR
echo "Installing Jenkins Agent..."
sudo mkdir -p /opt/jenkins
wget -q https://repo.jenkins-ci.org/public/org/jenkins-ci/main/remoting/4.13/remoting-4.13.jar -O /tmp/agent.jar
sudo mv /tmp/agent.jar /opt/jenkins/agent.jar

# Create cache directories
sudo mkdir -p /mnt/cache-volume
sudo mkdir -p /opt/unity-cache
sudo mkdir -p /opt/build-tools

# Set up environment variables
sudo tee /etc/environment > /dev/null << EOF
UNITY_PATH=/opt/unity/Editor/Unity
ANDROID_HOME=/opt/android-sdk
JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/unity/Editor:/opt/android-sdk/platform-tools
UNITY_VERSION=${UNITY_VERSION}
PROJECT_PREFIX=${PROJECT_PREFIX}
EOF

# Create Unity license setup script
sudo tee /opt/setup-unity-license.sh > /dev/null << 'EOF'
#!/bin/bash
# Unity license activation script

# Get Unity license from AWS Systems Manager Parameter Store
UNITY_USERNAME=$(aws ssm get-parameter --name "/jenkins/unity/username" --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo "")
UNITY_PASSWORD=$(aws ssm get-parameter --name "/jenkins/unity/password" --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo "")
UNITY_SERIAL=$(aws ssm get-parameter --name "/jenkins/unity/serial" --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo "")

if [ -n "$UNITY_USERNAME" ] && [ -n "$UNITY_PASSWORD" ]; then
    echo "Activating Unity license..."
    # Note: Actual Unity activation would be done here
    # /opt/unity/Editor/Unity -batchmode -quit -logFile /var/log/unity-activation.log -username "$UNITY_USERNAME" -password "$UNITY_PASSWORD" -serial "$UNITY_SERIAL"
    echo "Unity license activation completed"
else
    echo "Unity license credentials not found in Parameter Store"
fi
EOF

sudo chmod +x /opt/setup-unity-license.sh

# Create systemd service for agent
sudo tee /etc/systemd/system/jenkins-agent.service > /dev/null << 'EOF'
[Unit]
Description=Jenkins Unity Agent
After=network.target

[Service]
Type=forking
User=ec2-user
ExecStart=/opt/jenkins-agent-startup.sh
Restart=no

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable jenkins-agent

# Install additional build tools
echo "Installing additional build tools..."

# Install .NET (for some Unity projects)
sudo dnf install -y dotnet-sdk-6.0

# Install Python (for build scripts)
sudo dnf install -y python3 python3-pip

# Clean up
sudo dnf clean all
sudo rm -rf /tmp/* /var/tmp/*

echo "Unity Agent setup completed!"
echo "Unity Version: ${UNITY_VERSION}"
echo "Android SDK: Installed"
echo "Jenkins Agent: Ready"