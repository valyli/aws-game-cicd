"""IAM Stack for Jenkins Unity CI/CD."""

from aws_cdk import (
    Stack,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct
from typing import Dict, Any


class IamStack(Stack):
    """IAM Stack with roles and policies for Jenkins Master, Agents, and Lambda functions."""

    def __init__(self, scope: Construct, construct_id: str, config: Dict[str, Any], **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        
        # Create IAM roles
        self._create_jenkins_master_role()
        self._create_jenkins_agent_role()
        self._create_lambda_execution_role()

    def _create_jenkins_master_role(self):
        """Create IAM role for Jenkins Master EC2 instance."""
        
        self.jenkins_master_role = iam.Role(
            self, "JenkinsMasterRole",
            role_name=self.config["resource_namer"]("jenkins-master-role"),
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="IAM role for Jenkins Master EC2 instance",
        )
        
        # EC2 management permissions for Spot instances
        self.jenkins_master_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceStatus",
                    "ec2:DescribeSpotInstanceRequests",
                    "ec2:DescribeSpotFleetInstances",
                    "ec2:DescribeSpotFleetRequests",
                    "ec2:RequestSpotInstances",
                    "ec2:RequestSpotFleet",
                    "ec2:CancelSpotInstanceRequests",
                    "ec2:CancelSpotFleetRequests",
                    "ec2:TerminateInstances",
                    "ec2:RunInstances",
                    "ec2:CreateTags",
                    "ec2:DescribeImages",
                    "ec2:DescribeKeyPairs",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeVpcs",
                ],
                resources=["*"],
            )
        )
        
        # EFS access permissions
        self.jenkins_master_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "elasticfilesystem:DescribeFileSystems",
                    "elasticfilesystem:DescribeMountTargets",
                    "elasticfilesystem:ClientMount",
                    "elasticfilesystem:ClientWrite",
                    "elasticfilesystem:ClientRootAccess",
                ],
                resources=["*"],
            )
        )
        
        # S3 access permissions
        self.jenkins_master_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                ],
                resources=[
                    f"arn:aws:s3:::{self.config['project_prefix']}-*",
                    f"arn:aws:s3:::{self.config['project_prefix']}-*/*",
                ],
            )
        )
        
        # Lambda invocation permissions
        self.jenkins_master_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:InvokeFunction",
                ],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:{self.config['project_prefix']}-*",
                ],
            )
        )
        
        # CloudWatch Logs permissions
        self.jenkins_master_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/jenkins/*",
                ],
            )
        )
        
        # IAM permissions for managing agent instances
        self.jenkins_master_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "iam:PassRole",
                ],
                resources=[
                    f"arn:aws:iam::{self.account}:role/{self.config['project_prefix']}-jenkins-agent-role",
                ],
            )
        )
        
        # Create instance profile
        self.jenkins_master_instance_profile = iam.CfnInstanceProfile(
            self, "JenkinsMasterInstanceProfile",
            instance_profile_name=self.config["resource_namer"]("jenkins-master-instance-profile"),
            roles=[self.jenkins_master_role.role_name],
        )

    def _create_jenkins_agent_role(self):
        """Create IAM role for Jenkins Agent EC2 instances."""
        
        self.jenkins_agent_role = iam.Role(
            self, "JenkinsAgentRole",
            role_name=self.config["resource_namer"]("jenkins-agent-role"),
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="IAM role for Jenkins Agent EC2 instances",
        )
        
        # EBS volume management permissions
        self.jenkins_agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:AttachVolume",
                    "ec2:DetachVolume",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeVolumeStatus",
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceAttribute",
                    "ec2:ModifyInstanceAttribute",
                ],
                resources=["*"],
            )
        )
        
        # S3 access permissions
        self.jenkins_agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                ],
                resources=[
                    f"arn:aws:s3:::{self.config['project_prefix']}-*",
                    f"arn:aws:s3:::{self.config['project_prefix']}-*/*",
                ],
            )
        )
        
        # Lambda invocation permissions for cache pool management
        self.jenkins_agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:InvokeFunction",
                ],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:{self.config['project_prefix']}-allocate-cache-volume",
                    f"arn:aws:lambda:{self.region}:{self.account}:function:{self.config['project_prefix']}-release-cache-volume",
                ],
            )
        )
        
        # CloudWatch Logs permissions
        self.jenkins_agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/jenkins/agents/*",
                ],
            )
        )
        
        # Systems Manager permissions for Unity license
        self.jenkins_agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath",
                ],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/jenkins/unity/*",
                ],
            )
        )
        
        # Create instance profile
        self.jenkins_agent_instance_profile = iam.CfnInstanceProfile(
            self, "JenkinsAgentInstanceProfile",
            instance_profile_name=self.config["resource_namer"]("jenkins-agent-instance-profile"),
            roles=[self.jenkins_agent_role.role_name],
        )

    def _create_lambda_execution_role(self):
        """Create IAM role for Lambda functions."""
        
        self.lambda_execution_role = iam.Role(
            self, "LambdaExecutionRole",
            role_name=self.config["resource_namer"]("lambda-execution-role"),
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="IAM role for Lambda functions managing cache pool",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
            ],
        )
        
        # DynamoDB permissions
        self.lambda_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.config['project_prefix']}-cache-pool-status",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.config['project_prefix']}-cache-pool-status/index/*",
                ],
            )
        )
        
        # EC2 volume management permissions
        self.lambda_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:CreateVolume",
                    "ec2:DeleteVolume",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeVolumeStatus",
                    "ec2:AttachVolume",
                    "ec2:DetachVolume",
                    "ec2:ModifyVolumeAttribute",
                    "ec2:CreateSnapshot",
                    "ec2:DeleteSnapshot",
                    "ec2:DescribeSnapshots",
                    "ec2:CreateTags",
                    "ec2:DescribeInstances",
                    "ec2:DescribeAvailabilityZones",
                ],
                resources=["*"],
            )
        )
        
        # CloudWatch Logs permissions
        self.lambda_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/{self.config['project_prefix']}-*",
                ],
            )
        )

        # Outputs
        CfnOutput(
            self, "JenkinsMasterRoleArn",
            value=self.jenkins_master_role.role_arn,
            description="Jenkins Master IAM Role ARN",
            export_name=f"{self.config['project_prefix']}-jenkins-master-role-arn"
        )
        
        CfnOutput(
            self, "JenkinsAgentRoleArn",
            value=self.jenkins_agent_role.role_arn,
            description="Jenkins Agent IAM Role ARN",
            export_name=f"{self.config['project_prefix']}-jenkins-agent-role-arn"
        )
        
        CfnOutput(
            self, "LambdaExecutionRoleArn",
            value=self.lambda_execution_role.role_arn,
            description="Lambda Execution IAM Role ARN",
            export_name=f"{self.config['project_prefix']}-lambda-execution-role-arn"
        )