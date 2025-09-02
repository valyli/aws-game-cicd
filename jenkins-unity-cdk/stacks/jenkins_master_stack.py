"""Jenkins Master Stack for Jenkins Unity CI/CD."""

from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    Duration,
    CfnOutput,
)
from constructs import Construct
from typing import Dict, Any


class JenkinsMasterStack(Stack):
    """Jenkins Master Stack with EC2, Auto Scaling Group, and Application Load Balancer."""

    def __init__(self, scope: Construct, construct_id: str, config: Dict[str, Any], 
                 vpc_stack, storage_stack, iam_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        self.vpc_stack = vpc_stack
        self.storage_stack = storage_stack
        self.iam_stack = iam_stack
        
        # Create Jenkins Master infrastructure
        self._create_launch_template()
        self._create_auto_scaling_group()
        self._create_application_load_balancer()

    def _create_launch_template(self):
        """Create launch template for Jenkins Master."""
        
        # Build user data script
        user_data_script = self._build_user_data_script()

        self.launch_template = ec2.LaunchTemplate(
            self, "JenkinsMasterLaunchTemplate",
            launch_template_name=self.config["resource_namer"]("jenkins-master-lt"),
            instance_type=ec2.InstanceType(self.config["jenkins_master"]["instance_type"]),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=self.vpc_stack.jenkins_master_sg,
            role=self.iam_stack.jenkins_master_role,
            user_data=ec2.UserData.custom(user_data_script),
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=self.config["jenkins_master"]["volume_size"],
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    )
                )
            ],
            require_imdsv2=True,
        )

    def _build_user_data_script(self):
        """Build the user data script for Jenkins Master."""
        
        efs_id = self.storage_stack.jenkins_efs.file_system_id
        region = self.region
        project_prefix = self.config['project_prefix']
        
        script = f"""#!/bin/bash
# Set up logging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting Jenkins Master setup at $(date)"

# Update system
yum update -y

# Install SSM Agent (critical for remote access)
yum install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Install CloudWatch Agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Install Java first and verify (exact same command as manual success)
echo "Installing Java..."
yum install -y java-17-amazon-corretto

# Verify Java installation and fail if not working
echo "Verifying Java installation..."
if ! java -version 2>&1; then
    echo "ERROR: Java installation failed!"
    exit 1
fi

JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:bin/java::")
export JAVA_HOME
echo "JAVA_HOME=$JAVA_HOME" >> /etc/environment
echo "Java installed successfully at $JAVA_HOME"

# Install other dependencies
echo "Installing other dependencies..."
yum install -y git wget curl unzip htop amazon-efs-utils

# Install Jenkins
echo "Installing Jenkins..."
wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key
yum install -y jenkins

# Verify Jenkins installation
if [ ! -f /usr/share/java/jenkins.war ]; then
    echo "ERROR: Jenkins installation failed!"
    exit 1
fi

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Create EFS mount point
mkdir -p /var/lib/jenkins
chown jenkins:jenkins /var/lib/jenkins

# Mount EFS with retry logic
echo "{efs_id}.efs.{region}.amazonaws.com:/ /var/lib/jenkins efs defaults,_netdev" >> /etc/fstab
for i in $(seq 1 5); do
    if mount -a; then
        echo "EFS mounted successfully"
        break
    fi
    echo "EFS mount attempt $i/5 failed, retrying..."
    sleep 10
done

# Ensure correct permissions
chown -R jenkins:jenkins /var/lib/jenkins

# Configure Jenkins environment
echo "Configuring Jenkins environment..."
export JENKINS_HOME=/var/lib/jenkins
export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:bin/java::")

# Ensure correct permissions
chown -R jenkins:jenkins /var/lib/jenkins

# Try systemd first, fallback to manual
echo "Starting Jenkins with systemd..."
systemctl daemon-reload
systemctl enable jenkins

if systemctl start jenkins; then
    echo "Jenkins started successfully with systemd"
    JENKINS_START_METHOD="systemd"
else
    echo "Systemd failed, starting Jenkins manually..."
    sudo -u jenkins JAVA_HOME=$JAVA_HOME nohup java -Dhudson.security.csrf.GlobalCrumbIssuerConfiguration.DISABLE_CSRF_PROTECTION=true -Djava.awt.headless=true -jar /usr/share/java/jenkins.war --httpPort=8080 > /var/log/jenkins-manual.log 2>&1 &
    echo "Jenkins started manually"
    JENKINS_START_METHOD="manual"
fi

# Wait for Jenkins to be ready
echo "Waiting for Jenkins to start..."
for i in $(seq 1 30); do
    if netstat -tlnp | grep :8080; then
        echo "Jenkins is listening on port 8080"
        break
    fi
    echo "Waiting for Jenkins port... attempt $i/30"
    sleep 10
done

# Install Docker for build tools
yum install -y docker --allowerasing
systemctl enable docker
systemctl start docker
usermod -a -G docker jenkins

# Create Jenkins configuration (无安全模式)
mkdir -p /var/lib/jenkins

# 创建无安全模式的config.xml
cat > /var/lib/jenkins/config.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<hudson>
  <version>2.516.2</version>
  <numExecutors>2</numExecutors>
  <mode>NORMAL</mode>
  <useSecurity>false</useSecurity>
  <authorizationStrategy class="hudson.security.AuthorizationStrategy$Unsecured"/>
  <securityRealm class="hudson.security.SecurityRealm$None"/>
  <disableRememberMe>false</disableRememberMe>
  <workspaceDir>${{JENKINS_HOME}}/workspace/${{ITEM_FULLNAME}}</workspaceDir>
  <buildsDir>${{ITEM_ROOTDIR}}/builds</buildsDir>
  <jdks/>
  <views>
    <hudson.model.AllView>
      <owner class="hudson" reference="../../.."/>
      <name>all</name>
      <filterExecutors>false</filterExecutors>
      <filterQueue>false</filterQueue>
    </hudson.model.AllView>
  </views>
  <primaryView>all</primaryView>
  <slaveAgentPort>-1</slaveAgentPort>
  <clouds/>
</hudson>
EOF

# Configure Jenkins for Unity builds
cat > /var/lib/jenkins/jenkins.yaml << EOF
jenkins:
  systemMessage: "Unity CI/CD Jenkins Master - {project_prefix}"
  numExecutors: 2
  mode: NORMAL
  scmCheckoutRetryCount: 3
  
  clouds:
    - ec2:
        name: "unity-agents"
        region: "{region}"
        useInstanceProfileForCredentials: true

security:
  globalJobDslSecurityConfiguration:
    useScriptSecurity: false

unclassified:
  location:
    adminAddress: "admin@company.com"
    url: "https://jenkins.company.com/"
EOF

# Configure CloudWatch Agent
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'EOF'
{{
    "logs": {{
        "logs_collected": {{
            "files": {{
                "collect_list": [
                    {{
                        "file_path": "/var/log/jenkins/jenkins.log",
                        "log_group_name": "/aws/ec2/jenkins/application",
                        "log_stream_name": "{{{{instance_id}}}}"
                    }},
                    {{
                        "file_path": "/var/log/user-data.log",
                        "log_group_name": "/aws/ec2/jenkins/user-data",
                        "log_stream_name": "{{{{instance_id}}}}"
                    }}
                ]
            }}
        }}
    }}
}}
EOF

# Start CloudWatch Agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s

# 确保配置文件权限正确
chown jenkins:jenkins /var/lib/jenkins/config.xml
echo "Jenkins configured for no-security mode"

# Final status check
echo "Final Jenkins status check..."
sleep 30
systemctl status jenkins --no-pager
netstat -tlnp | grep :8080
curl -I http://localhost:8080/login || echo "Jenkins not responding on localhost:8080"

# Wait for Jenkins to generate initial password
echo "Waiting for Jenkins initial password..."
for i in $(seq 1 60); do
    if [ -f /var/lib/jenkins/.jenkins/secrets/initialAdminPassword ]; then
        JENKINS_PASSWORD=$(cat /var/lib/jenkins/.jenkins/secrets/initialAdminPassword)
        echo "=== JENKINS INITIAL PASSWORD ==="
        echo "Password: $JENKINS_PASSWORD"
        echo "=== JENKINS INITIAL PASSWORD ==="
        echo "Jenkins initial password: $JENKINS_PASSWORD" >> /var/log/jenkins-setup.log
        break
    fi
    echo "Waiting for password file... attempt $i/60"
    sleep 5
done

# Create script to auto-create JNLP nodes for agents
cat > /opt/create-agent-node.sh << 'SCRIPT'
#!/bin/bash
# Script to create JNLP agent nodes automatically
AGENT_NAME="$1"
if [ -z "$AGENT_NAME" ]; then
    echo "Usage: $0 <agent-name>"
    exit 1
fi

echo "Creating Jenkins node: $AGENT_NAME"

# Wait for Jenkins to be ready
for i in $(seq 1 30); do
    if curl -s http://localhost:8080/login | grep -q "Jenkins"; then
        break
    fi
    sleep 5
done

# Create node using Jenkins CLI
curl -X POST "http://localhost:8080/computer/doCreateItem" \
  --data "name=$AGENT_NAME" \
  --data "type=hudson.slaves.DumbSlave" \
  --data "mode=NORMAL" \
  --data "numExecutors=2" \
  --data "remoteFS=/opt/jenkins" \
  --data "labelString=unity linux" \
  --data "launcher.stapler-class=hudson.slaves.JNLPLauncher" \
  --data "retentionStrategy.stapler-class=hudson.slaves.RetentionStrategy\$Always" \
  2>/dev/null && echo "Node $AGENT_NAME created successfully" || echo "Node creation failed"
SCRIPT

chmod +x /opt/create-agent-node.sh

# Create service to monitor for new agents and auto-create nodes
cat > /opt/agent-monitor.sh << 'MONITOR'
#!/bin/bash
# Monitor for new agent instances and create corresponding Jenkins nodes
echo "Starting agent monitor..."

while true; do
    # Get list of running agent instances
    AGENT_INSTANCES=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=*unity-agent*" "Name=instance-state-name,Values=running" \
        --query "Reservations[].Instances[].InstanceId" \
        --output text 2>/dev/null)
    
    for INSTANCE_ID in $AGENT_INSTANCES; do
        AGENT_NAME="unity-agent-$INSTANCE_ID"
        
        # Check if node already exists in Jenkins
        if ! curl -s "http://localhost:8080/computer/$AGENT_NAME/" | grep -q "$AGENT_NAME"; then
            echo "Creating node for new agent: $AGENT_NAME"
            /opt/create-agent-node.sh "$AGENT_NAME"
        fi
    done
    
    sleep 30
done
MONITOR

chmod +x /opt/agent-monitor.sh

# Start agent monitor in background
nohup /opt/agent-monitor.sh > /var/log/agent-monitor.log 2>&1 &

# Log completion
echo "Jenkins Master setup completed at $(date)" | tee -a /var/log/jenkins-setup.log
echo "Setup completed successfully" > /tmp/setup-complete
"""
        return script

    def _create_auto_scaling_group(self):
        """Create Auto Scaling Group for Jenkins Master."""
        
        self.jenkins_master_asg = autoscaling.AutoScalingGroup(
            self, "JenkinsMasterASG",
            auto_scaling_group_name=self.config["resource_namer"]("jenkins-master-asg"),
            vpc=self.vpc_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC,
                availability_zones=[self.vpc_stack.vpc.availability_zones[0]]  # Deploy in first AZ only
            ),
            launch_template=self.launch_template,
            min_capacity=0,  # 暂时设为0以防止实例被替换
            max_capacity=1,
            desired_capacity=1,
            health_check=autoscaling.HealthCheck.ec2(
                grace=Duration.minutes(60)  # 延长宽限期，暂停替换
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                min_instances_in_service=0,
                max_batch_size=1,
                pause_time=Duration.minutes(5),
                wait_on_resource_signals=False,
            ),
        )

    def _create_application_load_balancer(self):
        """Create Application Load Balancer for Jenkins Master."""
        
        # Create ALB
        self.jenkins_alb = elbv2.ApplicationLoadBalancer(
            self, "JenkinsALB",
            load_balancer_name=self.config["resource_namer"]("jenkins-alb"),
            vpc=self.vpc_stack.vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            security_group=self.vpc_stack.alb_sg,
        )
        
        # Create target group
        self.jenkins_target_group = elbv2.ApplicationTargetGroup(
            self, "JenkinsTargetGroup",
            target_group_name=self.config["resource_namer"]("jenkins-tg"),
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=self.vpc_stack.vpc,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(
                enabled=True,
                healthy_http_codes="200,403,404",  # Jenkins returns 403 for unauthenticated health checks
                interval=Duration.seconds(60),
                path="/login",
                port="8080",
                protocol=elbv2.Protocol.HTTP,
                timeout=Duration.seconds(30),
                unhealthy_threshold_count=10,  # 更宽容的阈值
                healthy_threshold_count=2,
            ),
        )
        
        # Attach ASG to target group
        self.jenkins_master_asg.attach_to_application_target_group(self.jenkins_target_group)
        
        # Create HTTP listener (redirect to HTTPS)
        self.jenkins_alb.add_listener(
            "HTTPListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True,
            ),
        )
        
        # Create HTTP listener for Jenkins on port 8080
        self.jenkins_http_listener = self.jenkins_alb.add_listener(
            "JenkinsHTTPListener",
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.forward([self.jenkins_target_group]),
        )

        # Outputs
        CfnOutput(
            self, "JenkinsALBDNSName",
            value=self.jenkins_alb.load_balancer_dns_name,
            description="Jenkins Application Load Balancer DNS Name",
            export_name=f"{self.config['project_prefix']}-jenkins-alb-dns"
        )
        
        CfnOutput(
            self, "JenkinsURL",
            value=f"http://{self.jenkins_alb.load_balancer_dns_name}",
            description="Jenkins Web Interface URL",
            export_name=f"{self.config['project_prefix']}-jenkins-url"
        )
        
        CfnOutput(
            self, "JenkinsASGName",
            value=self.jenkins_master_asg.auto_scaling_group_name,
            description="Jenkins Master Auto Scaling Group Name",
            export_name=f"{self.config['project_prefix']}-jenkins-asg-name"
        )