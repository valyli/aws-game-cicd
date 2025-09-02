"""Jenkins Agent Stack for Jenkins Unity CI/CD."""

from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    Duration,
    CfnOutput,
)
from constructs import Construct
from typing import Dict, Any


class JenkinsAgentStack(Stack):
    """Jenkins Agent Stack with Spot instances and cache volume management."""

    def __init__(self, scope: Construct, construct_id: str, config: Dict[str, Any], 
                 vpc_stack, storage_stack, iam_stack, lambda_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        self.vpc_stack = vpc_stack
        self.storage_stack = storage_stack
        self.iam_stack = iam_stack
        self.lambda_stack = lambda_stack
        
        # Create Jenkins Agent infrastructure
        self._create_launch_template()
        self._create_auto_scaling_group()

    def _create_launch_template(self):
        """Create launch template for Jenkins Agents with Spot instances."""
        
        # 简化的 Agent 启动脚本
        user_data_script = f"""#!/bin/bash
# Set up logging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting Jenkins Agent setup at $(date)"

# Update system
yum update -y

# Install SSM Agent
yum install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Install Java
echo "Installing Java..."
yum install -y java-17-amazon-corretto
java -version

# Install basic dependencies
yum install -y git wget curl unzip

# Create jenkins user
useradd -m -s /bin/bash jenkins || true
mkdir -p /opt/jenkins
chown jenkins:jenkins /opt/jenkins

echo "Basic setup completed"
"""

        
        
        # 简化的 Jenkins Agent 连接脚本
        user_data_script += f"""
# Setup Jenkins Agent
echo "Setting up Jenkins Agent..."

# Use Jenkins Master private IP for internal communication
JENKINS_URL="http://10.0.0.66:8080"
echo "Jenkins URL: $JENKINS_URL"

# Get instance info
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
AGENT_NAME="unity-agent-$INSTANCE_ID"

echo "Agent Name: $AGENT_NAME"

# Wait for Jenkins to be ready
echo "Waiting for Jenkins to be ready..."
for i in $(seq 1 20); do
    if curl -s "$JENKINS_URL/login" > /dev/null 2>&1; then
        echo "Jenkins is ready"
        break
    fi
    echo "Waiting for Jenkins... attempt $i/20"
    sleep 15
done

# Download agent.jar
echo "Downloading Jenkins agent.jar..."
cd /opt/jenkins
if curl -o agent.jar "$JENKINS_URL/jnlpJars/agent.jar"; then
    echo "Agent.jar downloaded successfully"
else
    echo "Failed to download agent.jar, but continuing..."
fi

# Create JNLP agent startup script with auto-registration
cat > /opt/jenkins/start-agent.sh << 'EOF'
#!/bin/bash
echo "Starting Jenkins JNLP Agent with auto-registration..."

JENKINS_URL="http://10.0.0.66:8080"
# Use IMDSv2 to get instance metadata
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -s)
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id)
AGENT_NAME="unity-agent-$INSTANCE_ID"
PRIVATE_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/local-ipv4)

echo "Agent Name: $AGENT_NAME"
echo "Private IP: $PRIVATE_IP"

cd /opt/jenkins

# Wait for Jenkins to be fully ready
echo "Waiting for Jenkins to be ready..."
for i in $(seq 1 30); do
    if curl -s "$JENKINS_URL/login" | grep -q "Jenkins"; then
        echo "Jenkins is ready"
        break
    fi
    echo "Waiting... attempt $i/30"
    sleep 10
done

# Create node via Jenkins API (using anonymous access for initial setup)
echo "Creating Jenkins node via API..."
NODE_CONFIG='<slave>
  <name>'$AGENT_NAME'</name>
  <description>Unity Build Agent - '$INSTANCE_ID'</description>
  <remoteFS>/opt/jenkins</remoteFS>
  <numExecutors>2</numExecutors>
  <mode>NORMAL</mode>
  <launcher class="hudson.slaves.JNLPLauncher">
    <workDirSettings>
      <disabled>false</disabled>
      <workDirPath></workDirPath>
      <internalDir>remoting</internalDir>
      <failIfWorkDirIsMissing>false</failIfWorkDirIsMissing>
    </workDirSettings>
  </launcher>
  <label>unity linux</label>
  <nodeProperties/>
</slave>'

# Wait for Jenkins Master to create the node
echo "Waiting for Jenkins Master to create node $AGENT_NAME..."
for i in $(seq 1 30); do
    if curl -s "$JENKINS_URL/computer/$AGENT_NAME/jenkins-agent.jnlp" | grep -q "<jnlp>"; then
        echo "Node $AGENT_NAME found in Jenkins"
        break
    fi
    echo "Waiting for node creation... attempt $i/30"
    sleep 10
done

# Connect with JNLP
echo "Connecting with JNLP to $JENKINS_URL/computer/$AGENT_NAME/jenkins-agent.jnlp"
java -jar agent.jar -jnlpUrl "$JENKINS_URL/computer/$AGENT_NAME/jenkins-agent.jnlp" -workDir /opt/jenkins
EOF

chmod +x /opt/jenkins/start-agent.sh
chown jenkins:jenkins /opt/jenkins/start-agent.sh

chmod +x /opt/jenkins/start-agent.sh
chown jenkins:jenkins /opt/jenkins/start-agent.sh

# Create systemd service for JNLP agent
cat > /etc/systemd/system/jenkins-agent.service << 'EOF'
[Unit]
Description=Jenkins JNLP Agent
After=network.target

[Service]
Type=simple
User=jenkins
WorkingDirectory=/opt/jenkins
ExecStart=/opt/jenkins/start-agent.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable jenkins-agent
systemctl start jenkins-agent

echo "Jenkins JNLP Agent service started"

echo "Jenkins Agent setup completed at $(date)"
echo "Setup completed successfully" > /tmp/setup-complete
"""

        # 使用预构建的Unity AMI或默认AMI
        if "unity_ami_id" in self.config and self.config["unity_ami_id"]:
            machine_image = ec2.MachineImage.generic_linux({
                self.region: self.config["unity_ami_id"]
            })
        else:
            machine_image = ec2.MachineImage.latest_amazon_linux2023()
            
        self.launch_template = ec2.LaunchTemplate(
            self, "JenkinsAgentLaunchTemplate",
            launch_template_name=self.config["resource_namer"]("jenkins-agent-lt"),
            machine_image=machine_image,
            security_group=self.vpc_stack.jenkins_agent_sg,
            role=self.iam_stack.jenkins_agent_role,
            user_data=ec2.UserData.custom(user_data_script),
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=50,  # OS disk
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    )
                )
            ],
            require_imdsv2=True,
        )

    def _create_auto_scaling_group(self):
        """Create Auto Scaling Group for Jenkins Agents with Spot instances."""
        
        # Create mixed instances policy for Spot instances
        self.jenkins_agent_asg = autoscaling.AutoScalingGroup(
            self, "JenkinsAgentASG",
            auto_scaling_group_name=self.config["resource_namer"]("jenkins-agent-asg"),
            vpc=self.vpc_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            mixed_instances_policy=autoscaling.MixedInstancesPolicy(
                launch_template=self.launch_template,
                instances_distribution=autoscaling.InstancesDistribution(
                    on_demand_base_capacity=0,
                    on_demand_percentage_above_base_capacity=0,  # 100% Spot
                    spot_instance_pools=4,
                ),
                launch_template_overrides=[
                    autoscaling.LaunchTemplateOverrides(
                        instance_type=ec2.InstanceType(instance_type)
                    ) for instance_type in self.config["jenkins_agents"]["instance_types"]
                ]
            ),
            min_capacity=self.config["jenkins_agents"]["min_instances"],
            max_capacity=self.config["jenkins_agents"]["max_instances"],
            desired_capacity=self.config["jenkins_agents"]["desired_capacity"],
            health_check=autoscaling.HealthCheck.ec2(
                grace=Duration.minutes(10)  # 延长健康检查宽限期
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                min_instances_in_service=0,
                max_batch_size=2,
                pause_time=Duration.minutes(2),
                wait_on_resource_signals=False,  # 不等待信号，避免Unity安装超时
            ),
        )

        # Add scaling policies
        self._add_scaling_policies()

        # Outputs
        CfnOutput(
            self, "JenkinsAgentASGName",
            value=self.jenkins_agent_asg.auto_scaling_group_name,
            description="Jenkins Agent Auto Scaling Group Name",
            export_name=f"{self.config['project_prefix']}-jenkins-agent-asg-name"
        )

    def _add_scaling_policies(self):
        """Add scaling policies for the Auto Scaling Group."""
        
        # Scale on CPU utilization
        self.jenkins_agent_asg.scale_on_cpu_utilization(
            "CPUScaling",
            target_utilization_percent=70,
        )