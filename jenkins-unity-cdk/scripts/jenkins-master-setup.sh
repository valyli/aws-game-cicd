#!/bin/bash
# Jenkins Master setup script for AMI building

set -e

echo "Starting Jenkins Master setup..."

# Update system
sudo dnf update -y

# Install Java 17
sudo dnf install -y java-17-amazon-corretto-devel

# Install Git and other tools
sudo dnf install -y git wget curl unzip amazon-efs-utils

# Install Jenkins
sudo wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
sudo rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key
sudo dnf install -y jenkins

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

# Install Docker
sudo dnf install -y docker
sudo systemctl enable docker
sudo usermod -a -G docker jenkins

# Create Jenkins directories
sudo mkdir -p /var/lib/jenkins
sudo mkdir -p /var/lib/jenkins/init.groovy.d
sudo chown -R jenkins:jenkins /var/lib/jenkins

# Enable Jenkins service
sudo systemctl enable jenkins

# Create basic security configuration
sudo tee /var/lib/jenkins/init.groovy.d/basic-security.groovy > /dev/null << 'EOF'
#!groovy
import jenkins.model.*
import hudson.security.*

def instance = Jenkins.getInstance()

// Create admin user
def hudsonRealm = new HudsonPrivateSecurityRealm(false)
hudsonRealm.createAccount("admin", "admin123")
instance.setSecurityRealm(hudsonRealm)

// Set authorization strategy
def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)

// Save configuration
instance.save()
EOF

# Create startup script
sudo tee /opt/jenkins-startup.sh > /dev/null << 'EOF'
#!/bin/bash
# Jenkins startup script

# Get EFS ID from environment or parameter store
EFS_ID=$(aws ssm get-parameter --name "/jenkins/efs/id" --query 'Parameter.Value' --output text 2>/dev/null || echo "")

if [ -n "$EFS_ID" ]; then
    # Mount EFS if not already mounted
    if ! mountpoint -q /var/lib/jenkins; then
        echo "$EFS_ID.efs.us-east-1.amazonaws.com:/ /var/lib/jenkins efs defaults,_netdev" >> /etc/fstab
        mount -a
    fi
fi

# Ensure correct permissions
chown -R jenkins:jenkins /var/lib/jenkins

# Start services
systemctl start docker
systemctl start jenkins

# Wait for Jenkins to start
sleep 30

# Install plugins if plugins.txt exists
if [ -f /var/lib/jenkins/plugins.txt ]; then
    java -jar /var/cache/jenkins/war/WEB-INF/jenkins-cli.jar -s http://localhost:8080/ -auth admin:admin123 install-plugin < /var/lib/jenkins/plugins.txt || true
fi
EOF

sudo chmod +x /opt/jenkins-startup.sh

# Create systemd service for startup script
sudo tee /etc/systemd/system/jenkins-startup.service > /dev/null << 'EOF'
[Unit]
Description=Jenkins Startup Script
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/jenkins-startup.sh
RemainAfterExit=yes
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable jenkins-startup

# Clean up
sudo dnf clean all
sudo rm -rf /tmp/* /var/tmp/*

echo "Jenkins Master setup completed!"