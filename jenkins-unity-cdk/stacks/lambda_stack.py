"""Lambda Stack for Jenkins Unity CI/CD."""

from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_ec2 as ec2,
    aws_logs as logs,
    Duration,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct
from typing import Dict, Any


class LambdaStack(Stack):
    """Lambda Stack with cache pool management functions."""

    def __init__(self, scope: Construct, construct_id: str, config: Dict[str, Any], 
                 vpc_stack, storage_stack, iam_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        self.vpc_stack = vpc_stack
        self.storage_stack = storage_stack
        self.iam_stack = iam_stack
        
        # Create Lambda functions
        self._create_allocate_cache_volume_function()
        self._create_release_cache_volume_function()
        self._create_maintain_cache_pool_function()
        
        # Create scheduled maintenance
        self._create_maintenance_schedule()

    def _create_allocate_cache_volume_function(self):
        """Create Lambda function to allocate cache volumes."""
        
        # Create log group with explicit removal policy
        allocate_log_group = logs.LogGroup(
            self, "AllocateCacheVolumeLogGroup",
            log_group_name=f"/aws/lambda/{self.config['resource_namer']('allocate-cache-volume')}",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )
        
        self.allocate_cache_volume_function = _lambda.Function(
            self, "AllocateCacheVolumeFunction",
            function_name=self.config["resource_namer"]("allocate-cache-volume"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/allocate_cache_volume"),
            timeout=Duration.minutes(5),
            memory_size=256,
            role=self.iam_stack.lambda_execution_role,
            vpc=self.vpc_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.vpc_stack.lambda_sg],
            log_group=allocate_log_group,
            environment={
                "CACHE_POOL_TABLE": self.storage_stack.cache_pool_table.table_name,
                "VOLUME_SIZE": str(self.config["cache_pool"]["volume_size"]),
                "VOLUME_TYPE": self.config["cache_pool"]["volume_type"],
                "IOPS": str(self.config["cache_pool"]["iops"]),
                "THROUGHPUT": str(self.config["cache_pool"]["throughput"]),
            },
            description="Allocate cache volumes for Jenkins agents",
        )

    def _create_release_cache_volume_function(self):
        """Create Lambda function to release cache volumes."""
        
        # Create log group with explicit removal policy
        release_log_group = logs.LogGroup(
            self, "ReleaseCacheVolumeLogGroup",
            log_group_name=f"/aws/lambda/{self.config['resource_namer']('release-cache-volume')}",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )
        
        self.release_cache_volume_function = _lambda.Function(
            self, "ReleaseCacheVolumeFunction",
            function_name=self.config["resource_namer"]("release-cache-volume"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/release_cache_volume"),
            timeout=Duration.minutes(10),
            memory_size=256,
            role=self.iam_stack.lambda_execution_role,
            vpc=self.vpc_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.vpc_stack.lambda_sg],
            log_group=release_log_group,
            environment={
                "CACHE_POOL_TABLE": self.storage_stack.cache_pool_table.table_name,
            },
            description="Release cache volumes from Jenkins agents",
        )

    def _create_maintain_cache_pool_function(self):
        """Create Lambda function to maintain cache pool."""
        
        # Create log group with explicit removal policy
        maintain_log_group = logs.LogGroup(
            self, "MaintainCachePoolLogGroup",
            log_group_name=f"/aws/lambda/{self.config['resource_namer']('maintain-cache-pool')}",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )
        
        self.maintain_cache_pool_function = _lambda.Function(
            self, "MaintainCachePoolFunction",
            function_name=self.config["resource_namer"]("maintain-cache-pool"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/maintain_cache_pool"),
            timeout=Duration.minutes(15),
            memory_size=512,
            role=self.iam_stack.lambda_execution_role,
            vpc=self.vpc_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.vpc_stack.lambda_sg],
            log_group=maintain_log_group,
            environment={
                "CACHE_POOL_TABLE": self.storage_stack.cache_pool_table.table_name,
                "MAX_AGE_DAYS": str(self.config["cache_pool"]["max_age_days"]),
                "MIN_VOLUMES_PER_AZ": str(self.config["cache_pool"]["min_volumes_per_az"]),
                "VOLUME_SIZE": str(self.config["cache_pool"]["volume_size"]),
                "VOLUME_TYPE": self.config["cache_pool"]["volume_type"],
                "IOPS": str(self.config["cache_pool"]["iops"]),
                "THROUGHPUT": str(self.config["cache_pool"]["throughput"]),
            },
            description="Maintain cache pool - cleanup and optimization",
        )

    def _create_maintenance_schedule(self):
        """Create scheduled maintenance for cache pool."""
        
        # Create EventBridge rule for daily maintenance
        maintenance_rule = events.Rule(
            self, "CachePoolMaintenanceRule",
            rule_name=self.config["resource_namer"]("cache-pool-maintenance"),
            description="Daily maintenance for cache pool",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",  # 2 AM UTC
                day="*",
                month="*",
                year="*"
            ),
        )
        
        # Add Lambda target
        maintenance_rule.add_target(
            targets.LambdaFunction(self.maintain_cache_pool_function)
        )

        # Outputs
        CfnOutput(
            self, "AllocateCacheVolumeFunctionArn",
            value=self.allocate_cache_volume_function.function_arn,
            description="Allocate Cache Volume Lambda Function ARN",
            export_name=f"{self.config['project_prefix']}-allocate-cache-volume-arn"
        )
        
        CfnOutput(
            self, "ReleaseCacheVolumeFunctionArn",
            value=self.release_cache_volume_function.function_arn,
            description="Release Cache Volume Lambda Function ARN",
            export_name=f"{self.config['project_prefix']}-release-cache-volume-arn"
        )
        
        CfnOutput(
            self, "MaintainCachePoolFunctionArn",
            value=self.maintain_cache_pool_function.function_arn,
            description="Maintain Cache Pool Lambda Function ARN",
            export_name=f"{self.config['project_prefix']}-maintain-cache-pool-arn"
        )