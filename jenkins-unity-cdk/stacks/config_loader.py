"""Configuration loader for Jenkins Unity CI/CD CDK project."""

import os
import yaml
from typing import Dict, Any
from aws_cdk import App


class ConfigLoader:
    """Load and manage configuration for the CDK application."""
    
    def __init__(self, app: App):
        self.app = app
        self._config = None
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file and CDK context."""
        if self._config is not None:
            return self._config
            
        # Get configuration file name from context
        config_file = self.app.node.try_get_context("config_file") or "default"
        
        # Load YAML configuration
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", f"{config_file}.yaml")
        
        try:
            with open(config_path, 'r') as f:
                self._config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Warning: Config file {config_path} not found, using defaults")
            self._config = self._get_default_config()
        
        # Override with CDK context values
        self._override_with_context()
        
        return self._config
    
    def _override_with_context(self):
        """Override configuration with CDK context values."""
        context_overrides = {
            "project_prefix": self.app.node.try_get_context("project_prefix"),
            "aws_region": self.app.node.try_get_context("aws_region"),
            "unity_version": self.app.node.try_get_context("unity_version"),
        }
        
        for key, value in context_overrides.items():
            if value is not None:
                self._config[key] = value
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "project_prefix": "unity-cicd",
            "aws_region": "us-east-1",
            "unity_version": "2023.2.20f1",
            "vpc": {
                "cidr": "10.0.0.0/16",
                "availability_zones": 3
            },
            "jenkins_master": {
                "instance_type": "c5.large",
                "volume_size": 20
            },
            "jenkins_agents": {
                "instance_types": ["c5.2xlarge", "c5.4xlarge", "m5.2xlarge"],
                "max_instances": 10,
                "min_instances": 0,
                "desired_capacity": 2
            },
            "cache_pool": {
                "volume_size": 100,
                "volume_type": "gp3",
                "iops": 3000,
                "throughput": 125,
                "min_volumes_per_az": 2,
                "max_age_days": 7
            },
            "efs": {
                "performance_mode": "generalPurpose",
                "throughput_mode": "provisioned",
                "provisioned_throughput": 100
            },
            "monitoring": {
                "enable_detailed_monitoring": True,
                "log_retention_days": 30,
                "enable_xray": False
            }
        }
    
    def get_resource_name(self, resource_type: str, identifier: str = "") -> str:
        """Generate resource name with project prefix."""
        config = self.load_config()
        prefix = config["project_prefix"]
        
        if identifier:
            return f"{prefix}-{resource_type}-{identifier}"
        else:
            return f"{prefix}-{resource_type}"
    
    def get_s3_bucket_name(self, bucket_type: str, account_id: str, region: str) -> str:
        """Generate unique S3 bucket name."""
        config = self.load_config()
        prefix = config["project_prefix"]
        
        # Use account ID and region to ensure uniqueness
        unique_suffix = f"{account_id}-{region}"
        bucket_name = f"{prefix}-{bucket_type}-{unique_suffix}"
        
        # Ensure S3 naming compliance
        return bucket_name.lower().replace("_", "-")