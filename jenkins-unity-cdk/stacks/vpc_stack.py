"""VPC Stack for Jenkins Unity CI/CD."""

from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct
from typing import Dict, Any


class VpcStack(Stack):
    """VPC Stack with public and private subnets across multiple AZs."""

    def __init__(self, scope: Construct, construct_id: str, config: Dict[str, Any], **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        
        # Create VPC
        self.vpc = ec2.Vpc(
            self, "VPC",
            vpc_name=config["resource_namer"]("vpc"),
            ip_addresses=ec2.IpAddresses.cidr(config["vpc"]["cidr"]),
            max_azs=config["vpc"]["availability_zones"],
            subnet_configuration=[
                # Public subnets for ALB, Jenkins Master, NAT Gateway
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                # Private subnets for Jenkins Agents
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
            nat_gateways=config["vpc"]["availability_zones"],
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # Create VPC Endpoints for cost optimization and security
        self._create_vpc_endpoints()
        
        # Create Security Groups
        self._create_security_groups()

        # Outputs
        CfnOutput(
            self, "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID",
            export_name=f"{config['project_prefix']}-vpc-id"
        )

    def _create_vpc_endpoints(self):
        """Create VPC endpoints for AWS services."""
        
        # S3 Gateway Endpoint
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)]
        )
        
        # DynamoDB Gateway Endpoint
        self.vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)]
        )

    def _create_security_groups(self):
        """Create security groups for different components."""
        
        # Jenkins Master Security Group
        self.jenkins_master_sg = ec2.SecurityGroup(
            self, "JenkinsMasterSG",
            vpc=self.vpc,
            description="Security group for Jenkins Master",
            security_group_name=self.config["resource_namer"]("jenkins-master-sg"),
            allow_all_outbound=True,
        )
        
        # Jenkins Agent Security Group
        self.jenkins_agent_sg = ec2.SecurityGroup(
            self, "JenkinsAgentSG",
            vpc=self.vpc,
            description="Security group for Jenkins Agents",
            security_group_name=self.config["resource_namer"]("jenkins-agent-sg"),
            allow_all_outbound=True,
        )
        
        # ALB Security Group
        self.alb_sg = ec2.SecurityGroup(
            self, "ALBSG",
            vpc=self.vpc,
            description="Security group for Application Load Balancer",
            security_group_name=self.config["resource_namer"]("alb-sg"),
            allow_all_outbound=False,
        )
        
        # EFS Security Group
        self.efs_sg = ec2.SecurityGroup(
            self, "EFSSG",
            vpc=self.vpc,
            description="Security group for EFS",
            security_group_name=self.config["resource_namer"]("efs-sg"),
            allow_all_outbound=False,
        )
        
        # Lambda Security Group
        self.lambda_sg = ec2.SecurityGroup(
            self, "LambdaSG",
            vpc=self.vpc,
            description="Security group for Lambda functions",
            security_group_name=self.config["resource_namer"]("lambda-sg"),
            allow_all_outbound=True,
        )
        
        # Configure security group rules
        self._configure_security_group_rules()
        
        # No cross-references needed with CIDR-based rules

    def _configure_security_group_rules(self):
        """Configure security group ingress and egress rules."""
        
        # Jenkins Master Security Group Rules
        # SSH access from anywhere (as per design decision)
        self.jenkins_master_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="SSH access"
        )
        
        # HTTP from ALB (using CIDR instead of SG reference)
        self.jenkins_master_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.config["vpc"]["cidr"]),
            connection=ec2.Port.tcp(8080),
            description="HTTP from VPC"
        )
        
        # JNLP from agents (using CIDR instead of SG reference)
        self.jenkins_master_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.config["vpc"]["cidr"]),
            connection=ec2.Port.tcp(50000),
            description="JNLP from VPC"
        )
        
        # Jenkins Agent Security Group Rules
        # SSH from VPC
        self.jenkins_agent_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.config["vpc"]["cidr"]),
            connection=ec2.Port.tcp(22),
            description="SSH from VPC"
        )
        
        # ALB Security Group Rules
        # HTTP from anywhere
        self.alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="HTTP from anywhere"
        )
        
        # HTTPS from anywhere
        self.alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="HTTPS from anywhere"
        )
        
        # EFS Security Group Rules
        # NFS from VPC
        self.efs_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.config["vpc"]["cidr"]),
            connection=ec2.Port.tcp(2049),
            description="NFS from VPC"
        )
