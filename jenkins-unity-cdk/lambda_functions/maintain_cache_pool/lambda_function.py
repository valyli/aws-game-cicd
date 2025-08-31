"""Lambda function to maintain the cache pool - cleanup and optimization."""

import json
import os
import boto3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2')

# Environment variables
CACHE_POOL_TABLE = os.environ.get('CACHE_POOL_TABLE', 'unity-cicd-cache-pool-status')
MAX_AGE_DAYS = int(os.environ.get('MAX_AGE_DAYS', '7'))
MIN_VOLUMES_PER_AZ = int(os.environ.get('MIN_VOLUMES_PER_AZ', '2'))
VOLUME_SIZE = int(os.environ.get('VOLUME_SIZE', '100'))
VOLUME_TYPE = os.environ.get('VOLUME_TYPE', 'gp3')
IOPS = int(os.environ.get('IOPS', '3000'))
THROUGHPUT = int(os.environ.get('THROUGHPUT', '125'))

# Get AZs dynamically
def get_availability_zones():
    try:
        ec2_client = boto3.client('ec2')
        response = ec2_client.describe_availability_zones()
        return [az['ZoneName'] for az in response['AvailabilityZones']]
    except Exception:
        return ['us-east-1a', 'us-east-1b', 'us-east-1c']  # fallback


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Maintain the cache pool by cleaning up old volumes and ensuring minimum capacity.
    
    Returns:
        {
            "statusCode": 200,
            "cleaned_volumes": 3,
            "created_volumes": 1,
            "snapshots_created": 2
        }
    """
    try:
        logger.info("Starting cache pool maintenance")
        
        results = {
            'cleaned_volumes': 0,
            'created_volumes': 0,
            'snapshots_created': 0,
            'errors': []
        }
        
        # 1. Clean up old unused volumes
        cleaned_count = cleanup_old_volumes()
        results['cleaned_volumes'] = cleaned_count
        
        # 2. Ensure minimum volumes per AZ
        created_count = ensure_minimum_volumes()
        results['created_volumes'] = created_count
        
        # 3. Create snapshots for backup
        snapshot_count = create_backup_snapshots()
        results['snapshots_created'] = snapshot_count
        
        # 4. Clean up old snapshots
        cleanup_old_snapshots()
        
        logger.info(f"Cache pool maintenance completed: {results}")
        return {
            'statusCode': 200,
            **results
        }
        
    except Exception as e:
        logger.error(f"Error in cache pool maintenance: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }


def cleanup_old_volumes() -> int:
    """Clean up volumes that haven't been used for MAX_AGE_DAYS."""
    try:
        table = dynamodb.Table(CACHE_POOL_TABLE)
        cutoff_time = int((datetime.utcnow() - timedelta(days=MAX_AGE_DAYS)).timestamp())
        
        # Scan for old available volumes
        response = table.scan(
            FilterExpression='#status = :status AND LastUsed < :cutoff',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={
                ':status': 'Available',
                ':cutoff': cutoff_time
            }
        )
        
        cleaned_count = 0
        for item in response['Items']:
            volume_id = item['VolumeId']
            
            try:
                # Create snapshot before deletion
                create_volume_snapshot(volume_id, f"Backup before cleanup - {datetime.utcnow().isoformat()}")
                
                # Delete the volume
                ec2.delete_volume(VolumeId=volume_id)
                
                # Remove from DynamoDB
                table.delete_item(Key={'VolumeId': volume_id})
                
                logger.info(f"Cleaned up old volume: {volume_id}")
                cleaned_count += 1
                
            except Exception as e:
                logger.error(f"Error cleaning up volume {volume_id}: {str(e)}")
                continue
        
        return cleaned_count
        
    except Exception as e:
        logger.error(f"Error in cleanup_old_volumes: {str(e)}")
        return 0


def ensure_minimum_volumes() -> int:
    """Ensure each AZ has minimum number of available volumes."""
    try:
        table = dynamodb.Table(CACHE_POOL_TABLE)
        created_count = 0
        
        for az in get_availability_zones():
            # Count available volumes in this AZ
            response = table.query(
                IndexName='AZ-Status-Index',
                KeyConditionExpression='AvailabilityZone = :az AND #status = :status',
                ExpressionAttributeNames={'#status': 'Status'},
                ExpressionAttributeValues={
                    ':az': az,
                    ':status': 'Available'
                }
            )
            
            available_count = len(response['Items'])
            needed_count = max(0, MIN_VOLUMES_PER_AZ - available_count)
            
            logger.info(f"AZ {az}: {available_count} available, need {needed_count} more")
            
            # Create needed volumes
            for i in range(needed_count):
                try:
                    volume_id = create_cache_volume(az)
                    logger.info(f"Created new cache volume in {az}: {volume_id}")
                    created_count += 1
                except Exception as e:
                    logger.error(f"Error creating volume in {az}: {str(e)}")
                    continue
        
        return created_count
        
    except Exception as e:
        logger.error(f"Error in ensure_minimum_volumes: {str(e)}")
        return 0


def create_cache_volume(availability_zone: str) -> str:
    """Create a new cache volume."""
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
                        {'Key': 'ProjectId', 'Value': 'unity-game'},
                        {'Key': 'ManagedBy', 'Value': 'Lambda-Maintenance'},
                    ]
                }
            ]
        )
        
        volume_id = response['VolumeId']
        
        # Wait for volume to be available
        ec2.get_waiter('volume_available').wait(VolumeIds=[volume_id])
        
        # Add to DynamoDB
        table = dynamodb.Table(CACHE_POOL_TABLE)
        table.put_item(
            Item={
                'VolumeId': volume_id,
                'Status': 'Available',
                'AvailabilityZone': availability_zone,
                'ProjectId': 'unity-game',
                'CreatedTime': int(datetime.utcnow().timestamp()),
                'LastUsed': int(datetime.utcnow().timestamp()),
                'CacheVersion': '1.0'
            }
        )
        
        return volume_id
        
    except Exception as e:
        logger.error(f"Error creating cache volume: {str(e)}")
        raise


def create_backup_snapshots() -> int:
    """Create snapshots of in-use volumes for backup."""
    try:
        table = dynamodb.Table(CACHE_POOL_TABLE)
        
        # Get in-use volumes
        response = table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={':status': 'InUse'}
        )
        
        snapshot_count = 0
        for item in response['Items']:
            volume_id = item['VolumeId']
            
            try:
                snapshot_id = create_volume_snapshot(
                    volume_id, 
                    f"Automated backup - {datetime.utcnow().isoformat()}"
                )
                logger.info(f"Created snapshot {snapshot_id} for volume {volume_id}")
                snapshot_count += 1
                
            except Exception as e:
                logger.error(f"Error creating snapshot for volume {volume_id}: {str(e)}")
                continue
        
        return snapshot_count
        
    except Exception as e:
        logger.error(f"Error in create_backup_snapshots: {str(e)}")
        return 0


def create_volume_snapshot(volume_id: str, description: str) -> str:
    """Create a snapshot of the specified volume."""
    try:
        response = ec2.create_snapshot(
            VolumeId=volume_id,
            Description=description,
            TagSpecifications=[
                {
                    'ResourceType': 'snapshot',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'unity-cicd-cache-backup-{volume_id}'},
                        {'Key': 'Project', 'Value': 'unity-cicd'},
                        {'Key': 'Purpose', 'Value': 'Cache-Backup'},
                        {'Key': 'SourceVolume', 'Value': volume_id},
                        {'Key': 'ManagedBy', 'Value': 'Lambda-Maintenance'},
                    ]
                }
            ]
        )
        
        return response['SnapshotId']
        
    except Exception as e:
        logger.error(f"Error creating snapshot: {str(e)}")
        raise


def cleanup_old_snapshots():
    """Clean up snapshots older than 30 days."""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        # Get snapshots owned by this account
        response = ec2.describe_snapshots(
            OwnerIds=['self'],
            Filters=[
                {'Name': 'tag:Project', 'Values': ['unity-cicd']},
                {'Name': 'tag:Purpose', 'Values': ['Cache-Backup']},
            ]
        )
        
        for snapshot in response['Snapshots']:
            start_time = snapshot['StartTime'].replace(tzinfo=None)
            
            if start_time < cutoff_date:
                try:
                    ec2.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    logger.info(f"Deleted old snapshot: {snapshot['SnapshotId']}")
                except Exception as e:
                    logger.error(f"Error deleting snapshot {snapshot['SnapshotId']}: {str(e)}")
                    continue
                    
    except Exception as e:
        logger.error(f"Error in cleanup_old_snapshots: {str(e)}")