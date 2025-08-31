#!/usr/bin/env python3
"""Jenkins Unity CI/CD CDK Application."""

import os
import aws_cdk as cdk
from stacks.config_loader import ConfigLoader
from stacks.vpc_stack import VpcStack
from stacks.storage_stack import StorageStack
from stacks.iam_stack import IamStack


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
    
    # Add tags to all resources
    cdk.Tags.of(app).add("Project", config["project_prefix"])
    cdk.Tags.of(app).add("Environment", "development")
    cdk.Tags.of(app).add("ManagedBy", "CDK")
    cdk.Tags.of(app).add("UnityVersion", config["unity_version"])
    
    app.synth()


if __name__ == "__main__":
    main()