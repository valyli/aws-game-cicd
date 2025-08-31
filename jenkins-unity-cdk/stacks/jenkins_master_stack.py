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
        
        # User data script for Jenkins Master
        user_data_script = f"""#!/bin/bash
# Update system
yum update -y

# Install dependencies
yum install -y java-17-amazon-corretto-devel git wget curl unzip amazon-efs-utils

# Install Jenkins
wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key
yum install -y jenkins

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Create EFS mount point
mkdir -p /var/lib/jenkins
chown jenkins:jenkins /var/lib/jenkins

# Mount EFS
echo "{self.storage_stack.jenkins_efs.file_system_id}.efs.{self.region}.amazonaws.com:/ /var/lib/jenkins efs defaults,_netdev" >> /etc/fstab
mount -a

# Ensure correct permissions
chown -R jenkins:jenkins /var/lib/jenkins

# Configure Jenkins
systemctl enable jenkins
systemctl start jenkins

# Install Docker for build tools
yum install -y docker
systemctl enable docker
systemctl start docker
usermod -a -G docker jenkins

# Create Jenkins initial configuration
mkdir -p /var/lib/jenkins/init.groovy.d

# Basic security configuration
cat > /var/lib/jenkins/init.groovy.d/basic-security.groovy << 'EOF'
#!groovy
import jenkins.model.*
import hudson.security.*
import jenkins.security.s2m.AdminWhitelistRule

def instance = Jenkins.getInstance()

// Create admin user
def hudsonRealm = new HudsonPrivateSecurityRealm(false)
hudsonRealm.createAccount("admin", "admin123")
instance.setSecurityRealm(hudsonRealm)

// Set authorization strategy
def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)

// Disable remoting
instance.getDescriptor("jenkins.CLI").get().setEnabled(false)

// Save configuration
instance.save()
EOF

# Configure Jenkins for Unity builds
cat > /var/lib/jenkins/jenkins.yaml << 'EOF'
jenkins:
  systemMessage: "Unity CI/CD Jenkins Master - {self.config['project_prefix']}"
  numExecutors: 2
  mode: NORMAL
  scmCheckoutRetryCount: 3
  
  clouds:
    - ec2:
        name: "unity-agents"
        region: "{self.region}"
        useInstanceProfileForCredentials: true

security:
  globalJobDslSecurityConfiguration:
    useScriptSecurity: false

unclassified:
  location:
    adminAddress: "admin@company.com"
    url: "https://jenkins.company.com/"
EOF

# Restart Jenkins to apply configuration
systemctl restart jenkins

# Signal completion
/opt/aws/bin/cfn-signal -e $? --stack {self.stack_name} --resource JenkinsMasterASG --region {self.region}
"""

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
            min_capacity=1,
            max_capacity=1,
            desired_capacity=1,
            health_check=autoscaling.HealthCheck.elb(
                grace=Duration.minutes(10)
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                min_instances_in_service=0,
                max_batch_size=1,
                pause_time=Duration.minutes(10),
                wait_on_resource_signals=True,
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
                healthy_http_codes="200,403",  # Jenkins returns 403 for unauthenticated health checks
                interval=Duration.seconds(30),
                path="/login",
                port="8080",
                protocol=elbv2.Protocol.HTTP,
                timeout=Duration.seconds(10),
                unhealthy_threshold_count=3,
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
        
        # Create HTTPS listener (for now, forward to HTTP backend)
        # Note: In production, you would add SSL certificate here
        self.jenkins_alb.add_listener(
            "HTTPSListener",
            port=443,
            protocol=elbv2.ApplicationProtocol.HTTP,  # Change to HTTPS when certificate is added
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