"""Lambda function to allocate cache volumes for Jenkins agents."""

import json
import os
import boto3
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2')

# Environment variables
CACHE_POOL_TABLE = os.environ.get('CACHE_POOL_TABLE', 'unity-cicd-cache-pool-status')
VOLUME_SIZE = int(os.environ.get('VOLUME_SIZE', '100'))
VOLUME_TYPE = os.environ.get('VOLUME_TYPE', 'gp3')
IOPS = int(os.environ.get('IOPS', '3000'))
THROUGHPUT = int(os.environ.get('THROUGHPUT', '125'))


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Allocate a cache volume for a Jenkins agent.
    
    Args:
        event: {
            "availability_zone": "us-east-1a",
            "project_id": "unity-game",
            "instance_id": "i-1234567890abcdef0"  # optional
        }
    
    Returns:
        {
            "statusCode": 200,
            "volume_id": "vol-1234567890abcdef0",
            "status": "Available|Created"
        }
    """
    try:
        # Parse input parameters
        availability_zone = event.get('availability_zone')
        project_id = event.get('project_id', 'unity-game')
        instance_id = event.get('instance_id')
        
        if not availability_zone:
            raise ValueError("availability_zone is required")
        
        logger.info(f"Allocating cache volume for AZ: {availability_zone}, Project: {project_id}")
        
        # Try to find an available volume
        volume_id = find_available_volume(availability_zone, project_id)
        
        if volume_id:
            # Mark volume as in use
            update_volume_status(volume_id, 'InUse', instance_id)
            logger.info(f"Allocated existing volume: {volume_id}")
            return {
                'statusCode': 200,
                'volume_id': volume_id,
                'status': 'Available'
            }
        else:
            # Create new volume
            volume_id = create_new_volume(availability_zone, project_id, instance_id)
            logger.info(f"Created new volume: {volume_id}")
            return {
                'statusCode': 200,
                'volume_id': volume_id,
                'status': 'Created'
            }
            
    except Exception as e:
        logger.error(f"Error allocating cache volume: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }


def find_available_volume(availability_zone: str, project_id: str) -> Optional[str]:
    """Find an available cache volume in the specified AZ."""
    try:
        table = dynamodb.Table(CACHE_POOL_TABLE)
        
        # Query by AZ and Status
        response = table.query(
            IndexName='AZ-Status-Index',
            KeyConditionExpression='AvailabilityZone = :az AND #status = :status',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={
                ':az': availability_zone,
                ':status': 'Available'
            },
            FilterExpression='ProjectId = :project_id',
            ExpressionAttributeValues={
                ':project_id': project_id
            },
            Limit=1
        )
        
        if response['Items']:
            return response['Items'][0]['VolumeId']
        
        return None
        
    except Exception as e:
        logger.error(f"Error finding available volume: {str(e)}")
        return None


def create_new_volume(availability_zone: str, project_id: str, instance_id: Optional[str] = None) -> str:
    """Create a new EBS volume for cache."""
    try:
        # Create EBS volume
        response = ec2.create_volume(
            Size=VOLUME_SIZE,
            VolumeType=VOLUME_TYPE,
            Iops=IOPS,
            Throughput=THROUGHPUT,
            AvailabilityZone=availability_zone,
            Encrypted=True,
            TagSpecifications=[
                {
                    'ResourceType': 'volume',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'unity-cicd-cache-{availability_zone}'},
                        {'Key': 'Project', 'Value': 'unity-cicd'},
                        {'Key': 'Purpose', 'Value': 'Jenkins-Cache'},
                        {'Key': 'ProjectId', 'Value': project_id},
                        {'Key': 'ManagedBy', 'Value': 'Lambda'},
                    ]
                }
            ]
        )
        
        volume_id = response['VolumeId']
        
        # Wait for volume to be available
        ec2.get_waiter('volume_available').wait(VolumeIds=[volume_id])
        
        # Add to DynamoDB
        add_volume_to_pool(volume_id, availability_zone, project_id, instance_id)
        
        return volume_id
        
    except Exception as e:
        logger.error(f"Error creating new volume: {str(e)}")
        raise


def add_volume_to_pool(volume_id: str, availability_zone: str, project_id: str, instance_id: Optional[str] = None):
    """Add volume to the cache pool tracking table."""
    try:
        table = dynamodb.Table(CACHE_POOL_TABLE)
        
        item = {
            'VolumeId': volume_id,
            'Status': 'InUse' if instance_id else 'Building',
            'AvailabilityZone': availability_zone,
            'ProjectId': project_id,
            'CreatedTime': int(datetime.utcnow().timestamp()),
            'LastUsed': int(datetime.utcnow().timestamp()),
            'CacheVersion': '1.0'
        }
        
        if instance_id:
            item['InstanceId'] = instance_id
        
        table.put_item(Item=item)
        
    except Exception as e:
        logger.error(f"Error adding volume to pool: {str(e)}")
        raise


def update_volume_status(volume_id: str, status: str, instance_id: Optional[str] = None):
    """Update volume status in DynamoDB."""
    try:
        table = dynamodb.Table(CACHE_POOL_TABLE)
        
        update_expression = 'SET #status = :status, LastUsed = :last_used'
        expression_values = {
            ':status': status,
            ':last_used': int(datetime.utcnow().timestamp())
        }
        expression_names = {'#status': 'Status'}
        
        if instance_id:
            update_expression += ', InstanceId = :instance_id'
            expression_values[':instance_id'] = instance_id
        elif status == 'Available':
            # Remove InstanceId when marking as available
            update_expression += ' REMOVE InstanceId'
        
        table.update_item(
            Key={'VolumeId': volume_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        
    except Exception as e:
        logger.error(f"Error updating volume status: {str(e)}")
        raise