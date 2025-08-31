"""Storage Stack for Jenkins Unity CI/CD."""

from aws_cdk import (
    Stack,
    aws_efs as efs,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    RemovalPolicy,
    CfnOutput,
    Size,
    Duration,
)
from constructs import Construct
from typing import Dict, Any


class StorageStack(Stack):
    """Storage Stack with EFS, DynamoDB, and S3 resources."""

    def __init__(self, scope: Construct, construct_id: str, config: Dict[str, Any], vpc_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        self.vpc_stack = vpc_stack
        
        # Create EFS file system for Jenkins data
        self._create_efs()
        
        # Create DynamoDB table for cache pool status
        self._create_dynamodb_table()
        
        # Create S3 buckets
        self._create_s3_buckets()

    def _create_efs(self):
        """Create EFS file system for Jenkins data storage."""
        
        self.jenkins_efs = efs.FileSystem(
            self, "JenkinsEFS",
            vpc=self.vpc_stack.vpc,
            file_system_name=self.config["resource_namer"]("jenkins-efs"),
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
            throughput_mode=efs.ThroughputMode.PROVISIONED,
            provisioned_throughput_per_second=Size.mebibytes(self.config["efs"]["provisioned_throughput"]),
            encrypted=True,
            removal_policy=RemovalPolicy.DESTROY,  # For development
            security_group=self.vpc_stack.efs_sg,
        )

        # Output EFS ID
        CfnOutput(
            self, "JenkinsEFSId",
            value=self.jenkins_efs.file_system_id,
            description="Jenkins EFS File System ID",
            export_name=f"{self.config['project_prefix']}-jenkins-efs-id"
        )

    def _create_dynamodb_table(self):
        """Create DynamoDB table for cache pool status management."""
        
        self.cache_pool_table = dynamodb.Table(
            self, "CachePoolStatusTable",
            table_name=self.config["resource_namer"]("cache-pool-status"),
            partition_key=dynamodb.Attribute(
                name="VolumeId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.DESTROY,  # For development
        )
        
        # Add Global Secondary Index for AZ-Status queries
        self.cache_pool_table.add_global_secondary_index(
            index_name="AZ-Status-Index",
            partition_key=dynamodb.Attribute(
                name="AvailabilityZone",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Status",
                type=dynamodb.AttributeType.STRING
            ),
        )
        
        # Add Global Secondary Index for Project-Status queries
        self.cache_pool_table.add_global_secondary_index(
            index_name="Project-Status-Index",
            partition_key=dynamodb.Attribute(
                name="ProjectId",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Status",
                type=dynamodb.AttributeType.STRING
            ),
        )

        # Output table name
        CfnOutput(
            self, "CachePoolTableName",
            value=self.cache_pool_table.table_name,
            description="Cache Pool Status DynamoDB Table Name",
            export_name=f"{self.config['project_prefix']}-cache-pool-table-name"
        )

    def _create_s3_buckets(self):
        """Create S3 buckets for build artifacts, cache templates, and logs."""
        
        # Build artifacts bucket
        self.build_artifacts_bucket = s3.Bucket(
            self, "BuildArtifactsBucket",
            bucket_name=self.config["s3_bucket_namer"]("build-artifacts"),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,  # For development
            auto_delete_objects=True,  # For development
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    enabled=True,
                    noncurrent_version_expiration=Duration.days(30),
                ),
                s3.LifecycleRule(
                    id="TransitionToIA",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30),
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        ),
                    ],
                ),
            ],
        )
        
        # Cache templates bucket
        self.cache_templates_bucket = s3.Bucket(
            self, "CacheTemplatesBucket",
            bucket_name=self.config["s3_bucket_namer"]("cache-templates"),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,  # For development
            auto_delete_objects=True,  # For development
        )
        
        # Logs bucket
        self.logs_bucket = s3.Bucket(
            self, "LogsBucket",
            bucket_name=self.config["s3_bucket_namer"]("logs"),
            encryption=s3.BucketEncryption.S3_MANAGED,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,  # For development
            auto_delete_objects=True,  # For development
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldLogs",
                    enabled=True,
                    expiration=Duration.days(self.config["monitoring"]["log_retention_days"]),
                ),
            ],
        )

        # Outputs
        CfnOutput(
            self, "BuildArtifactsBucketName",
            value=self.build_artifacts_bucket.bucket_name,
            description="Build Artifacts S3 Bucket Name",
            export_name=f"{self.config['project_prefix']}-build-artifacts-bucket"
        )
        
        CfnOutput(
            self, "CacheTemplatesBucketName",
            value=self.cache_templates_bucket.bucket_name,
            description="Cache Templates S3 Bucket Name",
            export_name=f"{self.config['project_prefix']}-cache-templates-bucket"
        )
        
        CfnOutput(
            self, "LogsBucketName",
            value=self.logs_bucket.bucket_name,
            description="Logs S3 Bucket Name",
            export_name=f"{self.config['project_prefix']}-logs-bucket"
        )