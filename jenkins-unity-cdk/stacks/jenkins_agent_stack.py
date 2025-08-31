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
        
        # User data script for Jenkins Agent
        user_data_script = f"""#!/bin/bash
# Update system
yum update -y

# Install dependencies
yum install -y java-17-amazon-corretto-devel git wget curl unzip docker

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Configure Docker
systemctl enable docker
systemctl start docker
usermod -a -G docker ec2-user

# Install Unity Hub and Editor (placeholder - will be in AMI)
# This will be handled by the Unity Agent AMI

# Get instance metadata
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)
REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)

# Allocate cache volume
echo "Allocating cache volume..."
VOLUME_RESPONSE=$(aws lambda invoke \
    --region $REGION \
    --function-name {self.config["resource_namer"]("allocate-cache-volume")} \
    --payload '{{"availability_zone":"'$AZ'","project_id":"unity-game","instance_id":"'$INSTANCE_ID'"}}' \
    --output text \
    /tmp/volume_response.json)

VOLUME_ID=$(cat /tmp/volume_response.json | python3 -c "import sys, json; print(json.load(sys.stdin).get('volume_id', ''))")

if [ ! -z "$VOLUME_ID" ]; then
    echo "Allocated volume: $VOLUME_ID"
    
    # Wait for volume to be available
    aws ec2 wait volume-available --region $REGION --volume-ids $VOLUME_ID
    
    # Attach volume
    aws ec2 attach-volume \
        --region $REGION \
        --volume-id $VOLUME_ID \
        --instance-id $INSTANCE_ID \
        --device /dev/sdf
    
    # Wait for attachment
    aws ec2 wait volume-in-use --region $REGION --volume-ids $VOLUME_ID
    
    # Mount volume
    mkdir -p /mnt/cache
    
    # Check if volume has filesystem
    if ! blkid /dev/xvdf; then
        mkfs.ext4 /dev/xvdf
    fi
    
    mount /dev/xvdf /mnt/cache
    chown ec2-user:ec2-user /mnt/cache
    
    # Add to fstab for persistence
    echo "/dev/xvdf /mnt/cache ext4 defaults,nofail 0 2" >> /etc/fstab
    
    echo "Cache volume mounted successfully"
else
    echo "Failed to allocate cache volume"
fi

# Setup Spot interruption handler
cat > /opt/spot-interruption-handler.sh << 'EOF'
#!/bin/bash
# Monitor for Spot interruption notice
while true; do
    if curl -s http://169.254.169.254/latest/meta-data/spot/instance-action 2>/dev/null; then
        echo "Spot interruption notice received"
        
        # Get instance and volume info
        INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
        REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)
        
        # Find attached cache volume
        VOLUME_ID=$(aws ec2 describe-volumes \
            --region $REGION \
            --filters "Name=attachment.instance-id,Values=$INSTANCE_ID" "Name=tag:Purpose,Values=Jenkins-Cache" \
            --query "Volumes[0].VolumeId" \
            --output text)
        
        if [ "$VOLUME_ID" != "None" ] && [ ! -z "$VOLUME_ID" ]; then
            echo "Releasing cache volume: $VOLUME_ID"
            
            # Unmount volume
            umount /mnt/cache || true
            
            # Release volume via Lambda
            aws lambda invoke \
                --region $REGION \
                --function-name {self.config["resource_namer"]("release-cache-volume")} \
                --payload '{{"volume_id":"'$VOLUME_ID'","instance_id":"'$INSTANCE_ID'"}}' \
                /tmp/release_response.json
        fi
        
        # Graceful shutdown
        shutdown -h +2
        break
    fi
    sleep 5
done
EOF

chmod +x /opt/spot-interruption-handler.sh

# Start spot interruption handler
nohup /opt/spot-interruption-handler.sh > /var/log/spot-handler.log 2>&1 &

# Install Jenkins agent (will connect to master)
# This will be handled by Jenkins master when it discovers the agent

# Signal completion
/opt/aws/bin/cfn-signal -e $? --stack {self.stack_name} --resource JenkinsAgentASG --region {self.region}
"""

        self.launch_template = ec2.LaunchTemplate(
            self, "JenkinsAgentLaunchTemplate",
            launch_template_name=self.config["resource_namer"]("jenkins-agent-lt"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
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
                grace=Duration.minutes(5)
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                min_instances_in_service=0,
                max_batch_size=2,
                pause_time=Duration.minutes(5),
                wait_on_resource_signals=True,
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