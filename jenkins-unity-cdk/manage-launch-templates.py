#!/usr/bin/env python3
"""
Jenkins Agent Launch Template Management Script
用于创建、更新和管理Jenkins Agent的Launch Templates
"""

import boto3
import base64
import json
import argparse
from pathlib import Path

class LaunchTemplateManager:
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.config = {
            'security_group_id': 'sg-0cae1c773589f67ba',
            'iam_instance_profile': 'unity-cicd-jenkins-agent-instance-profile',
            'subnet_id': 'subnet-02ac9ed0cfe66207b'
        }
    
    def read_userdata_script(self, script_path):
        """读取用户数据脚本"""
        with open(script_path, 'r') as f:
            return f.read()
    
    def create_launch_template(self, name, image_id, instance_type, userdata_script, platform, volume_size=20):
        """创建Launch Template"""
        userdata_encoded = base64.b64encode(userdata_script.encode()).decode()
        
        device_name = '/dev/xvda' if platform == 'linux' else '/dev/sda1'
        
        try:
            response = self.ec2.create_launch_template(
                LaunchTemplateName=name,
                LaunchTemplateData={
                    'ImageId': image_id,
                    'InstanceType': instance_type,
                    'SecurityGroupIds': [self.config['security_group_id']],
                    'IamInstanceProfile': {
                        'Name': self.config['iam_instance_profile']
                    },
                    'UserData': userdata_encoded,
                    'TagSpecifications': [
                        {
                            'ResourceType': 'instance',
                            'Tags': [
                                {'Key': 'Name', 'Value': f'jenkins-{platform}-agent-auto'},
                                {'Key': 'Type', 'Value': 'JenkinsAgent'},
                                {'Key': 'Platform', 'Value': platform.title()}
                            ]
                        }
                    ],
                    'BlockDeviceMappings': [
                        {
                            'DeviceName': device_name,
                            'Ebs': {
                                'VolumeSize': volume_size,
                                'VolumeType': 'gp3',
                                'DeleteOnTermination': True,
                                'Encrypted': True
                            }
                        }
                    ]
                }
            )
            print(f"✅ Created Launch Template: {name}")
            print(f"   Template ID: {response['LaunchTemplate']['LaunchTemplateId']}")
            return response['LaunchTemplate']['LaunchTemplateId']
        except Exception as e:
            if 'AlreadyExistsException' in str(e):
                print(f"⚠️  Launch Template {name} already exists")
                return None
            else:
                raise e
    
    def update_launch_template(self, name, userdata_script):
        """更新Launch Template（创建新版本）"""
        userdata_encoded = base64.b64encode(userdata_script.encode()).decode()
        
        # 获取原始模板配置
        try:
            original_response = self.ec2.describe_launch_template_versions(
                LaunchTemplateName=name,
                Versions=['1']  # 使用版本1，它有完整配置
            )
            original = original_response['LaunchTemplateVersions'][0]['LaunchTemplateData']
            
            # 更新UserData但保留其他配置
            original['UserData'] = userdata_encoded
            
            response = self.ec2.create_launch_template_version(
                LaunchTemplateName=name,
                LaunchTemplateData=original
            )
            version = response['LaunchTemplateVersion']['VersionNumber']
            print(f"✅ Updated Launch Template: {name}")
            print(f"   New Version: {version}")
            
            # 设置为默认版本
            self.ec2.modify_launch_template(
                LaunchTemplateName=name,
                DefaultVersion=str(version)
            )
            print(f"   Set as default version: {version}")
            return version
        except Exception as e:
            print(f"❌ Failed to update {name}: {e}")
            return None
    
    def delete_launch_template(self, name):
        """删除Launch Template"""
        try:
            self.ec2.delete_launch_template(LaunchTemplateName=name)
            print(f"✅ Deleted Launch Template: {name}")
        except Exception as e:
            print(f"❌ Failed to delete {name}: {e}")
    
    def list_launch_templates(self):
        """列出所有Jenkins相关的Launch Templates"""
        try:
            response = self.ec2.describe_launch_templates()
            jenkins_templates = [
                lt for lt in response['LaunchTemplates'] 
                if 'jenkins' in lt['LaunchTemplateName'].lower()
            ]
            
            if jenkins_templates:
                print("📋 Jenkins Launch Templates:")
                for lt in jenkins_templates:
                    print(f"   - {lt['LaunchTemplateName']} (ID: {lt['LaunchTemplateId']})")
                    print(f"     Default Version: {lt['DefaultVersionNumber']}")
                    print(f"     Latest Version: {lt['LatestVersionNumber']}")
            else:
                print("📋 No Jenkins Launch Templates found")
        except Exception as e:
            print(f"❌ Failed to list templates: {e}")
    
    def launch_instance(self, template_name, count=1):
        """使用Launch Template启动实例"""
        try:
            response = self.ec2.run_instances(
                LaunchTemplate={'LaunchTemplateName': template_name},
                SubnetId=self.config['subnet_id'],
                MinCount=count,
                MaxCount=count
            )
            
            instance_ids = [i['InstanceId'] for i in response['Instances']]
            print(f"🚀 Launched {count} instance(s) using {template_name}:")
            for iid in instance_ids:
                print(f"   - {iid}")
            return instance_ids
        except Exception as e:
            print(f"❌ Failed to launch instance: {e}")
            return []

def main():
    parser = argparse.ArgumentParser(description='Manage Jenkins Agent Launch Templates')
    parser.add_argument('action', choices=['create', 'update', 'delete', 'list', 'launch'], 
                       help='Action to perform')
    parser.add_argument('--platform', choices=['linux', 'windows'], 
                       help='Platform type (for create/update)')
    parser.add_argument('--name', help='Launch Template name')
    parser.add_argument('--count', type=int, default=1, help='Number of instances to launch')
    
    args = parser.parse_args()
    manager = LaunchTemplateManager()
    
    if args.action == 'create':
        # 预定义配置
        configs = {
            'linux': {
                'name': 'jenkins-linux-agent-template',
                'image_id': 'ami-0c02fb55956c7d316',  # Amazon Linux 2023
                'instance_type': 't3.medium',
                'script_path': 'linux-jnlp-agent-userdata.sh',
                'volume_size': 20
            },
            'windows': {
                'name': 'jenkins-windows-agent-template', 
                'image_id': 'ami-028dc1123403bd543',  # Windows Server 2022
                'instance_type': 'c5.large',
                'script_path': 'windows-jnlp-agent-userdata.ps1',
                'volume_size': 50
            }
        }
        
        if args.platform:
            config = configs[args.platform]
            script = manager.read_userdata_script(config['script_path'])
            manager.create_launch_template(
                config['name'], config['image_id'], config['instance_type'],
                script, args.platform, config['volume_size']
            )
        else:
            # 创建所有平台
            for platform, config in configs.items():
                script = manager.read_userdata_script(config['script_path'])
                manager.create_launch_template(
                    config['name'], config['image_id'], config['instance_type'],
                    script, platform, config['volume_size']
                )
    
    elif args.action == 'update':
        if not args.platform:
            print("❌ --platform required for update")
            return
        
        script_files = {
            'linux': 'linux-jnlp-agent-userdata.sh',
            'windows': 'windows-jnlp-agent-userdata.ps1'
        }
        
        template_names = {
            'linux': 'jenkins-linux-agent-template',
            'windows': 'jenkins-windows-agent-template'
        }
        
        script = manager.read_userdata_script(script_files[args.platform])
        manager.update_launch_template(template_names[args.platform], script)
    
    elif args.action == 'delete':
        if not args.name:
            print("❌ --name required for delete")
            return
        manager.delete_launch_template(args.name)
    
    elif args.action == 'list':
        manager.list_launch_templates()
    
    elif args.action == 'launch':
        if not args.name:
            print("❌ --name required for launch")
            return
        manager.launch_instance(args.name, args.count)

if __name__ == "__main__":
    main()