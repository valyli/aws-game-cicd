"""Lambda function to release cache volumes from Jenkins agents."""

import json
import os
import boto3
import logging
from datetime import datetime
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2')

# Environment variables
CACHE_POOL_TABLE = os.environ.get('CACHE_POOL_TABLE', 'unity-cicd-cache-pool-status')


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Release a cache volume from a Jenkins agent.
    
    Args:
        event: {
            "volume_id": "vol-1234567890abcdef0",
            "instance_id": "i-1234567890abcdef0"
        }
    
    Returns:
        {
            "statusCode": 200,
            "message": "Volume released successfully"
        }
    """
    try:
        # Parse input parameters
        volume_id = event.get('volume_id')
        instance_id = event.get('instance_id')
        
        if not volume_id:
            raise ValueError("volume_id is required")
        
        logger.info(f"Releasing cache volume: {volume_id} from instance: {instance_id}")
        
        # Detach volume from instance if attached
        if instance_id:
            detach_volume_from_instance(volume_id, instance_id)
        
        # Update volume status to Available
        update_volume_status(volume_id, 'Available')
        
        logger.info(f"Successfully released volume: {volume_id}")
        return {
            'statusCode': 200,
            'message': 'Volume released successfully'
        }
        
    except Exception as e:
        logger.error(f"Error releasing cache volume: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }


def detach_volume_from_instance(volume_id: str, instance_id: str):
    """Detach EBS volume from EC2 instance."""
    try:
        # Check if volume is attached
        response = ec2.describe_volumes(VolumeIds=[volume_id])
        volume = response['Volumes'][0]
        
        # Find attachment to the specified instance
        for attachment in volume.get('Attachments', []):
            if attachment['InstanceId'] == instance_id and attachment['State'] in ['attached', 'attaching']:
                logger.info(f"Detaching volume {volume_id} from instance {instance_id}")
                
                # Detach volume
                ec2.detach_volume(
                    VolumeId=volume_id,
                    InstanceId=instance_id,
                    Force=False  # Graceful detach
                )
                
                # Wait for volume to be available
                ec2.get_waiter('volume_available').wait(
                    VolumeIds=[volume_id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 60}
                )
                
                logger.info(f"Volume {volume_id} successfully detached")
                break
        else:
            logger.info(f"Volume {volume_id} is not attached to instance {instance_id}")
            
    except Exception as e:
        logger.error(f"Error detaching volume: {str(e)}")
        # Don't raise exception here, continue with status update
        # The volume might already be detached


def update_volume_status(volume_id: str, status: str):
    """Update volume status in DynamoDB."""
    try:
        table = dynamodb.Table(CACHE_POOL_TABLE)
        
        # Update status and remove instance ID
        table.update_item(
            Key={'VolumeId': volume_id},
            UpdateExpression='SET #status = :status, LastUsed = :last_used REMOVE InstanceId',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={
                ':status': status,
                ':last_used': int(datetime.utcnow().timestamp())
            }
        )
        
        logger.info(f"Updated volume {volume_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Error updating volume status: {str(e)}")
        raise


def validate_volume_exists(volume_id: str) -> bool:
    """Validate that the volume exists in AWS."""
    try:
        response = ec2.describe_volumes(VolumeIds=[volume_id])
        return len(response['Volumes']) > 0
    except ec2.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'InvalidVolume.NotFound':
            return False
        raise