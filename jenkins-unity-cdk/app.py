#!/usr/bin/env python3
"""Jenkins Unity CI/CD CDK Application."""

import os
import aws_cdk as cdk
from stacks.config_loader import ConfigLoader
from stacks.vpc_stack import VpcStack
from stacks.storage_stack import StorageStack
from stacks.iam_stack import IamStack
from stacks.lambda_stack import LambdaStack
from stacks.jenkins_master_stack import JenkinsMasterStack
from stacks.jenkins_agent_stack import JenkinsAgentStack
from stacks.monitoring_stack import MonitoringStack


def main():
    """Main application entry point."""
    app = cdk.App()
    
    # Load configuration
    config_loader = ConfigLoader(app)
    config = config_loader.load_config()
    
    # Add resource naming helper to config
    config["resource_namer"] = lambda resource_type, identifier="": config_loader.get_resource_name(resource_type, identifier)
    config["s3_bucket_namer"] = lambda bucket_type: config_loader.get_s3_bucket_name(
        bucket_type, 
        app.account, 
        config["aws_region"]
    )
    
    # Environment configuration
    env = cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=config["aws_region"]
    )
    
    # Create VPC Stack
    vpc_stack = VpcStack(
        app, 
        config["resource_namer"]("vpc-stack"),
        config=config,
        env=env,
        description=f"VPC infrastructure for {config['project_prefix']} Jenkins Unity CI/CD"
    )
    
    # Create Storage Stack
    storage_stack = StorageStack(
        app,
        config["resource_namer"]("storage-stack"),
        config=config,
        vpc_stack=vpc_stack,
        env=env,
        description=f"Storage infrastructure for {config['project_prefix']} Jenkins Unity CI/CD"
    )
    storage_stack.add_dependency(vpc_stack)
    
    # Create IAM Stack
    iam_stack = IamStack(
        app,
        config["resource_namer"]("iam-stack"),
        config=config,
        env=env,
        description=f"IAM roles and policies for {config['project_prefix']} Jenkins Unity CI/CD"
    )
    
    # Create Lambda Stack
    lambda_stack = LambdaStack(
        app,
        config["resource_namer"]("lambda-stack"),
        config=config,
        vpc_stack=vpc_stack,
        storage_stack=storage_stack,
        iam_stack=iam_stack,
        env=env,
        description=f"Lambda functions for {config['project_prefix']} Jenkins Unity CI/CD"
    )
    lambda_stack.add_dependency(vpc_stack)
    lambda_stack.add_dependency(storage_stack)
    lambda_stack.add_dependency(iam_stack)
    
    # Create Jenkins Master Stack
    jenkins_master_stack = JenkinsMasterStack(
        app,
        config["resource_namer"]("jenkins-master-stack"),
        config=config,
        vpc_stack=vpc_stack,
        storage_stack=storage_stack,
        iam_stack=iam_stack,
        env=env,
        description=f"Jenkins Master infrastructure for {config['project_prefix']} Jenkins Unity CI/CD"
    )
    jenkins_master_stack.add_dependency(vpc_stack)
    jenkins_master_stack.add_dependency(storage_stack)
    jenkins_master_stack.add_dependency(iam_stack)
    
    # Create Jenkins Agent Stack
    jenkins_agent_stack = JenkinsAgentStack(
        app,
        config["resource_namer"]("jenkins-agent-stack"),
        config=config,
        vpc_stack=vpc_stack,
        storage_stack=storage_stack,
        iam_stack=iam_stack,
        lambda_stack=lambda_stack,
        env=env,
        description=f"Jenkins Agent infrastructure for {config['project_prefix']} Jenkins Unity CI/CD"
    )
    jenkins_agent_stack.add_dependency(vpc_stack)
    jenkins_agent_stack.add_dependency(storage_stack)
    jenkins_agent_stack.add_dependency(iam_stack)
    jenkins_agent_stack.add_dependency(lambda_stack)
    
    # Create Monitoring Stack
    monitoring_stack = MonitoringStack(
        app,
        config["resource_namer"]("monitoring-stack"),
        config=config,
        vpc_stack=vpc_stack,
        storage_stack=storage_stack,
        lambda_stack=lambda_stack,
        jenkins_master_stack=jenkins_master_stack,
        jenkins_agent_stack=jenkins_agent_stack,
        env=env,
        description=f"Monitoring infrastructure for {config['project_prefix']} Jenkins Unity CI/CD"
    )
    monitoring_stack.add_dependency(vpc_stack)
    monitoring_stack.add_dependency(storage_stack)
    monitoring_stack.add_dependency(lambda_stack)
    monitoring_stack.add_dependency(jenkins_master_stack)
    monitoring_stack.add_dependency(jenkins_agent_stack)
    
    # Add tags to all resources
    cdk.Tags.of(app).add("Project", config["project_prefix"])
    cdk.Tags.of(app).add("Environment", config.get("environment", "development"))
    cdk.Tags.of(app).add("ManagedBy", "CDK")
    cdk.Tags.of(app).add("UnityVersion", config["unity_version"])
    
    app.synth()


if __name__ == "__main__":
    main()