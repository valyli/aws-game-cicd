"""Monitoring Stack for Jenkins Unity CI/CD."""

from aws_cdk import (
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
    aws_sns as sns,
    aws_cloudwatch_actions as cw_actions,
    Duration,
    CfnOutput,
)
from constructs import Construct
from typing import Dict, Any


class MonitoringStack(Stack):
    """Monitoring Stack with CloudWatch dashboards, alarms, and log groups."""

    def __init__(self, scope: Construct, construct_id: str, config: Dict[str, Any], 
                 vpc_stack, storage_stack, lambda_stack, jenkins_master_stack, jenkins_agent_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        self.vpc_stack = vpc_stack
        self.storage_stack = storage_stack
        self.lambda_stack = lambda_stack
        self.jenkins_master_stack = jenkins_master_stack
        self.jenkins_agent_stack = jenkins_agent_stack
        
        # Create monitoring resources
        self._create_log_groups()
        self._create_sns_topics()
        self._create_custom_metrics()
        self._create_alarms()
        self._create_dashboard()

    def _create_log_groups(self):
        """Create CloudWatch log groups for different components."""
        
        # Jenkins Master log group
        self.jenkins_master_log_group = logs.LogGroup(
            self, "JenkinsMasterLogGroup",
            log_group_name=f"/aws/jenkins/master/{self.config['project_prefix']}",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        
        # Jenkins Agents log group
        self.jenkins_agents_log_group = logs.LogGroup(
            self, "JenkinsAgentsLogGroup",
            log_group_name=f"/aws/jenkins/agents/{self.config['project_prefix']}",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        
        # Cache Pool Lambda log groups are created automatically by Lambda functions

    def _create_sns_topics(self):
        """Create SNS topics for alerts."""
        
        self.alerts_topic = sns.Topic(
            self, "AlertsTopic",
            topic_name=self.config["resource_namer"]("alerts"),
            display_name="Jenkins Unity CI/CD Alerts",
        )

        # Output SNS topic ARN for manual subscription
        CfnOutput(
            self, "AlertsTopicArn",
            value=self.alerts_topic.topic_arn,
            description="SNS Topic ARN for alerts - subscribe to receive notifications",
            export_name=f"{self.config['project_prefix']}-alerts-topic-arn"
        )

    def _create_custom_metrics(self):
        """Create custom CloudWatch metrics."""
        
        # Cache pool metrics will be published by Lambda functions
        # Jenkins metrics will be published by Jenkins plugins
        pass

    def _create_alarms(self):
        """Create CloudWatch alarms for monitoring."""
        
        # Jenkins Master CPU alarm
        jenkins_master_cpu_alarm = cloudwatch.Alarm(
            self, "JenkinsMasterHighCPU",
            alarm_name=self.config["resource_namer"]("jenkins-master-high-cpu"),
            alarm_description="Jenkins Master high CPU utilization",
            metric=cloudwatch.Metric(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions_map={
                    "AutoScalingGroupName": self.jenkins_master_stack.jenkins_master_asg.auto_scaling_group_name
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        jenkins_master_cpu_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alerts_topic)
        )
        
        # Jenkins Agents CPU alarm
        jenkins_agents_cpu_alarm = cloudwatch.Alarm(
            self, "JenkinsAgentsHighCPU",
            alarm_name=self.config["resource_namer"]("jenkins-agents-high-cpu"),
            alarm_description="Jenkins Agents high CPU utilization",
            metric=cloudwatch.Metric(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions_map={
                    "AutoScalingGroupName": self.jenkins_agent_stack.jenkins_agent_asg.auto_scaling_group_name
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=90,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        jenkins_agents_cpu_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alerts_topic)
        )
        
        # EFS throughput alarm
        efs_throughput_alarm = cloudwatch.Alarm(
            self, "EFSHighThroughput",
            alarm_name=self.config["resource_namer"]("efs-high-throughput"),
            alarm_description="EFS high throughput utilization",
            metric=cloudwatch.Metric(
                namespace="AWS/EFS",
                metric_name="TotalIOBytes",
                dimensions_map={
                    "FileSystemId": self.storage_stack.jenkins_efs.file_system_id
                },
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=80 * 1024 * 1024,  # 80 MB/s
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        efs_throughput_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alerts_topic)
        )
        
        # Lambda function error alarms
        for function_name, function in [
            ("allocate-cache-volume", self.lambda_stack.allocate_cache_volume_function),
            ("release-cache-volume", self.lambda_stack.release_cache_volume_function),
            ("maintain-cache-pool", self.lambda_stack.maintain_cache_pool_function),
        ]:
            error_alarm = cloudwatch.Alarm(
                self, f"Lambda{function_name.replace('-', '')}Errors",
                alarm_name=self.config["resource_namer"](f"lambda-{function_name}-errors"),
                alarm_description=f"Lambda function {function_name} errors",
                metric=function.metric_errors(
                    period=Duration.minutes(5),
                    statistic="Sum",
                ),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            )
            error_alarm.add_alarm_action(
                cw_actions.SnsAction(self.alerts_topic)
            )
        
        # DynamoDB throttling alarm
        dynamodb_throttle_alarm = cloudwatch.Alarm(
            self, "DynamoDBThrottling",
            alarm_name=self.config["resource_namer"]("dynamodb-throttling"),
            alarm_description="DynamoDB cache pool table throttling",
            metric=cloudwatch.Metric(
                namespace="AWS/DynamoDB",
                metric_name="ThrottledRequests",
                dimensions_map={
                    "TableName": self.storage_stack.cache_pool_table.table_name
                },
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        dynamodb_throttle_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alerts_topic)
        )

    def _create_dashboard(self):
        """Create CloudWatch dashboard for monitoring."""
        
        self.dashboard = cloudwatch.Dashboard(
            self, "JenkinsUnityDashboard",
            dashboard_name=self.config["resource_namer"]("dashboard"),
        )
        
        # Jenkins Master metrics
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Jenkins Master - CPU & Memory",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/EC2",
                        metric_name="CPUUtilization",
                        dimensions_map={
                            "AutoScalingGroupName": self.jenkins_master_stack.jenkins_master_asg.auto_scaling_group_name
                        },
                        statistic="Average",
                        period=Duration.minutes(5),
                    )
                ],
                right=[
                    cloudwatch.Metric(
                        namespace="AWS/EC2",
                        metric_name="MemoryUtilization",
                        dimensions_map={
                            "AutoScalingGroupName": self.jenkins_master_stack.jenkins_master_asg.auto_scaling_group_name
                        },
                        statistic="Average",
                        period=Duration.minutes(5),
                    )
                ],
                width=12,
                height=6,
            )
        )
        
        # Jenkins Agents metrics
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Jenkins Agents - Instance Count & CPU",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/AutoScaling",
                        metric_name="GroupDesiredCapacity",
                        dimensions_map={
                            "AutoScalingGroupName": self.jenkins_agent_stack.jenkins_agent_asg.auto_scaling_group_name
                        },
                        statistic="Average",
                        period=Duration.minutes(5),
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/AutoScaling",
                        metric_name="GroupInServiceInstances",
                        dimensions_map={
                            "AutoScalingGroupName": self.jenkins_agent_stack.jenkins_agent_asg.auto_scaling_group_name
                        },
                        statistic="Average",
                        period=Duration.minutes(5),
                    )
                ],
                right=[
                    cloudwatch.Metric(
                        namespace="AWS/EC2",
                        metric_name="CPUUtilization",
                        dimensions_map={
                            "AutoScalingGroupName": self.jenkins_agent_stack.jenkins_agent_asg.auto_scaling_group_name
                        },
                        statistic="Average",
                        period=Duration.minutes(5),
                    )
                ],
                width=12,
                height=6,
            )
        )
        
        # EFS metrics
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="EFS - Throughput & Operations",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/EFS",
                        metric_name="TotalIOBytes",
                        dimensions_map={
                            "FileSystemId": self.storage_stack.jenkins_efs.file_system_id
                        },
                        statistic="Sum",
                        period=Duration.minutes(5),
                    )
                ],
                right=[
                    cloudwatch.Metric(
                        namespace="AWS/EFS",
                        metric_name="TotalIOOperations",
                        dimensions_map={
                            "FileSystemId": self.storage_stack.jenkins_efs.file_system_id
                        },
                        statistic="Sum",
                        period=Duration.minutes(5),
                    )
                ],
                width=12,
                height=6,
            )
        )
        
        # Lambda functions metrics
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Functions - Duration & Errors",
                left=[
                    self.lambda_stack.allocate_cache_volume_function.metric_duration(
                        statistic="Average",
                        period=Duration.minutes(5),
                    ),
                    self.lambda_stack.release_cache_volume_function.metric_duration(
                        statistic="Average",
                        period=Duration.minutes(5),
                    ),
                    self.lambda_stack.maintain_cache_pool_function.metric_duration(
                        statistic="Average",
                        period=Duration.minutes(5),
                    )
                ],
                right=[
                    self.lambda_stack.allocate_cache_volume_function.metric_errors(
                        statistic="Sum",
                        period=Duration.minutes(5),
                    ),
                    self.lambda_stack.release_cache_volume_function.metric_errors(
                        statistic="Sum",
                        period=Duration.minutes(5),
                    ),
                    self.lambda_stack.maintain_cache_pool_function.metric_errors(
                        statistic="Sum",
                        period=Duration.minutes(5),
                    )
                ],
                width=12,
                height=6,
            )
        )
        
        # DynamoDB metrics
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="DynamoDB - Cache Pool Table",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ConsumedReadCapacityUnits",
                        dimensions_map={
                            "TableName": self.storage_stack.cache_pool_table.table_name
                        },
                        statistic="Sum",
                        period=Duration.minutes(5),
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ConsumedWriteCapacityUnits",
                        dimensions_map={
                            "TableName": self.storage_stack.cache_pool_table.table_name
                        },
                        statistic="Sum",
                        period=Duration.minutes(5),
                    )
                ],
                right=[
                    cloudwatch.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ThrottledRequests",
                        dimensions_map={
                            "TableName": self.storage_stack.cache_pool_table.table_name
                        },
                        statistic="Sum",
                        period=Duration.minutes(5),
                    )
                ],
                width=12,
                height=6,
            )
        )

        # Output dashboard URL
        CfnOutput(
            self, "DashboardURL",
            value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name={self.dashboard.dashboard_name}",
            description="CloudWatch Dashboard URL",
            export_name=f"{self.config['project_prefix']}-dashboard-url"
        )