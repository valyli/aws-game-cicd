# Jenkins Unity CI/CD 系统设计文档

## 1. 项目概述

### 1.1 项目目标
在AWS上构建一个专门用于Unity游戏项目CI/CD的Jenkins系统，通过使用Spot实例和EBS缓存池技术，在保证构建效率的同时显著降低成本。

### 1.2 核心需求
- **Jenkins控制节点**: 使用EC2 On-Demand实例部署，确保稳定性和灵活控制
- **Jenkins Agent节点**: 使用Spot实例降低成本，支持Unity项目构建
- **缓存优化**: 通过EBS缓存池避免每次1小时+的环境初始化时间
- **高可用性**: 多AZ部署，确保系统稳定运行
- **成本优化**: Spot实例节省60-90%计算成本

### 1.3 技术约束
- Unity项目 + Git仓库 + 依赖总大小: 几十GB
- 环境初始化时间: 超过1小时
- 单次构建时间: 30分钟 - 1小时
- Spot实例中断后可接受重新开始构建

## 2. 系统架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    VPC (Multi-AZ)                                      │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                            Public Subnets                                          │  │
│  │                                                                                     │  │
│  │ ┌─────────────┐    ┌─────────────────────────────────┐    ┌─────────────┐         │  │
│  │ │     ALB     │    │      Jenkins Master             │    │ NAT Gateway │         │  │
│  │ │             │◄───┤      (EC2 On-Demand)           │    │             │         │  │
│  │ └─────────────┘    │      直接SSH访问                │    └─────────────┘         │  │
│  │                    └─────────────────────────────────┘                            │  │
│  │                                  │                                                 │  │
│  │                                  ▼                                                 │  │
│  │                    ┌─────────────────────────────────┐                            │  │
│  │                    │             EFS                 │                            │  │
│  │                    │       (Jenkins Data)            │                            │  │
│  │                    └─────────────────────────────────┘                            │  │
│  └─────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                         Private Subnets                                            │  │
│  │              Spot Instance Auto Scaling Groups                                     │  │
│  │                                                                                     │  │
│  │ AZ-1a              AZ-1b              AZ-1c                                         │  │
│  │ ┌───────────┐      ┌───────────┐      ┌───────────┐                               │  │
│  │ │Agent 1    │      │Agent 3    │      │Agent 5    │                               │  │
│  │ │+ Cache EBS│      │+ Cache EBS│      │+ Cache EBS│                               │  │
│  │ └───────────┘      └───────────┘      └───────────┘                               │  │
│  │ ┌───────────┐      ┌───────────┐      ┌───────────┐                               │  │
│  │ │Agent 2    │      │Agent 4    │      │Agent 6    │                               │  │
│  │ │+ Cache EBS│      │+ Cache EBS│      │+ Cache EBS│                               │  │
│  │ └───────────┘      └───────────┘      └───────────┘                               │  │
│  └─────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   支撑服务                                               │
│                                                                                         │
│ ┌─────────────┐    ┌─────────────┐    ┌───────────────────────────────────────────────┐ │
│ │  DynamoDB   │    │     S3      │    │              CloudWatch                       │ │
│ │(缓存池状态)  │    │ (构建产物)   │    │            (监控 & 日志)                       │ │
│ └─────────────┘    └─────────────┘    └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 网络架构设计

#### 2.2.1 架构决策说明

**选择方案: 公有子网 + 严格安全控制**

经过对比分析，我们选择将Jenkins Master部署在公有子网中，原因如下：

```
方案对比:
│ 特性         │ 私有子网+EIP │ 公有子网+安全组 │
├─────────────┼─────────────────┼─────────────────────┤
│ 调试便利性   │ ★★★           │ ★★★★★             │
│ 安全性       │ ★★★★★         │ ★★★★              │
│ 成本         │ +$3.6/月       │ $0                │
│ 配置复杂度   │ 高             │ 中                │
│ 维护难度     │ 高             │ 低                │
└─────────────┴─────────────────┴─────────────────────┘
```

**决策理由:**
1. **调试便利性**: 直接SSH访问，无需复杂的EIP路由配置
2. **成本优化**: 节省EIP成本($3.6/月)
3. **安全可控**: 通过严格的安全组规则控制访问
4. **运维简化**: 减少网络配置复杂度

**安全措施:**
- SSH访问依赖密钥认证，禁用密码登录
- 使用强密钥对和定期轮换
- 启用fail2ban防止暴力破解
- 定期安全更新和漏洞扫描
- CloudTrail记录所有API调用

### 2.2.2 网络组件

#### 2.2.1 VPC配置
- **CIDR**: 10.0.0.0/16
- **可用区**: 3个AZ (us-east-1a, us-east-1b, us-east-1c)

#### 2.2.3 子网配置
```
Public Subnets:
- 10.0.1.0/24 (us-east-1a) - ALB, Jenkins Master, NAT Gateway
- 10.0.2.0/24 (us-east-1b) - ALB, NAT Gateway  
- 10.0.3.0/24 (us-east-1c) - ALB, NAT Gateway

Private Subnets:
- 10.0.11.0/24 (us-east-1a) - Spot Agents
- 10.0.12.0/24 (us-east-1b) - Spot Agents
- 10.0.13.0/24 (us-east-1c) - Spot Agents

注意: Jenkins Master部署在公有子网，便于调试和维护
```

#### 2.2.4 安全组配置
```
Jenkins Master Security Group:
- Inbound: 
  - Port 8080 from ALB Security Group (HTTP)
  - Port 22 from 0.0.0.0/0 (SSH - 直接访问)
  - Port 50000 from Agent Security Group (JNLP)
- Outbound: All traffic

ALB Security Group:
- Inbound:
  - Port 80 from 0.0.0.0/0 (HTTP)
  - Port 443 from 0.0.0.0/0 (HTTPS)
- Outbound: Port 8080 to Jenkins Master

Agent Security Group:
- Inbound:
  - Port 22 from Jenkins Master (SSH)
- Outbound: All traffic

EFS Security Group:
- Inbound:
  - Port 2049 from Jenkins Master Security Group
- Outbound: None
```

## 3. Jenkins Master设计

### 3.1 EC2实例配置
- **实例类型**: c5.large (2 vCPU, 4 GB RAM)
- **存储**: 20GB gp3 根卷
- **网络**: 部署在Public Subnet (us-east-1a)
- **公网IP**: 自动分配公网IP
- **Auto Scaling Group**: 最小1个实例，确保高可用
- **访问方式**: 
  - Web访问: 通过ALB (HTTPS)
  - SSH访问: 直接通过公网IP (端口22)

### 3.2 Jenkins数据存储
- **存储方案**: Amazon EFS
- **挂载点**: /var/lib/jenkins
- **性能模式**: General Purpose
- **吞吐量模式**: Provisioned (100 MiB/s)
- **加密**: 启用传输和静态加密

### 3.3 Jenkins配置管理
- **配置方式**: Jenkins Configuration as Code (JCasC)
- **插件管理**: 预装必需插件到AMI
- **配置文件**: 存储在EFS，支持热更新

### 3.4 必需插件列表
```yaml
required_plugins:
  - unity3d-plugin          # Unity构建支持
  - git                     # Git集成
  - pipeline-stage-view     # Pipeline可视化
  - build-timeout           # 构建超时控制
  - timestamper            # 时间戳
  - ws-cleanup             # 工作空间清理
  - ec2                    # EC2插件
  - spot-fleet             # Spot Fleet管理
  - workflow-aggregator    # Pipeline支持
  - blueocean              # 现代UI
```

## 4. EBS缓存池系统设计

### 4.1 缓存池架构

#### 4.1.1 设计原理
- **核心思想**: 预创建包含Unity项目缓存的EBS卷，Spot实例启动时直接挂载使用
- **工作方式**: Spot实例直接在挂载的EBS卷上进行构建工作，无需额外同步
- **回收机制**: Spot实例终止时，EBS卷自动归还到缓存池供下次使用

#### 4.1.2 缓存池结构
```
EBS缓存池管理系统
├── DynamoDB状态表
│   ├── VolumeId (主键)
│   ├── Status (Available/InUse/Building/Maintenance)
│   ├── AvailabilityZone
│   ├── LastUsed (时间戳)
│   ├── ProjectId (项目标识)
│   └── CacheVersion (缓存版本)
├── 分AZ缓存池
│   ├── AZ-1a Pool (3-5个卷)
│   ├── AZ-1b Pool (3-5个卷)
│   └── AZ-1c Pool (3-5个卷)
└── Lambda管理函数
    ├── 卷分配函数
    ├── 卷回收函数
    └── 清理维护函数
```

### 4.2 EBS卷规格
- **卷类型**: gp3
- **卷大小**: 100GB (适应几十GB Unity项目需求)
- **IOPS**: 3000 (基准性能)
- **吞吐量**: 125 MiB/s
- **加密**: 启用

### 4.3 缓存内容结构
```
/mnt/cache-volume/
├── unity-projects/          # Unity项目文件
│   └── [project-name]/
├── git-repos/              # Git仓库缓存
│   └── [repo-name].git/
├── unity-cache/            # Unity编辑器缓存
│   ├── Library/
│   └── Temp/
├── build-tools/            # 构建工具
│   └── unity-editor/
└── dependencies/           # 项目依赖
    ├── packages/
    └── assets/
```

### 4.4 缓存池管理逻辑

#### 4.4.1 卷分配流程
```python
def allocate_cache_volume(availability_zone, project_id):
    """
    为新的Spot实例分配缓存卷
    """
    # 1. 查询DynamoDB找到指定AZ的可用卷
    available_volumes = query_available_volumes(availability_zone, project_id)
    
    # 2. 如果有可用卷，直接分配
    if available_volumes:
        volume_id = available_volumes[0]['VolumeId']
        update_volume_status(volume_id, 'InUse')
        return volume_id
    
    # 3. 如果没有可用卷，创建新卷
    volume_id = create_new_cache_volume(availability_zone, project_id)
    return volume_id

def create_new_cache_volume(availability_zone, project_id):
    """
    创建新的缓存卷并初始化
    """
    # 1. 创建EBS卷
    volume_id = ec2.create_volume(
        Size=100,
        VolumeType='gp3',
        AvailabilityZone=availability_zone,
        Encrypted=True
    )
    
    # 2. 更新DynamoDB状态
    update_volume_status(volume_id, 'Building')
    
    # 3. 触发初始化流程
    trigger_cache_initialization(volume_id, project_id)
    
    return volume_id
```

#### 4.4.2 卷回收流程
```python
def release_cache_volume(volume_id, instance_id):
    """
    回收Spot实例使用的缓存卷
    """
    # 1. 从实例分离卷
    ec2.detach_volume(VolumeId=volume_id, InstanceId=instance_id)
    
    # 2. 等待分离完成
    wait_for_volume_available(volume_id)
    
    # 3. 更新状态为可用
    update_volume_status(volume_id, 'Available')
    
    # 4. 记录最后使用时间
    update_last_used_time(volume_id)
```

#### 4.4.3 缓存维护流程
```python
def maintain_cache_pool():
    """
    定期维护缓存池
    """
    # 1. 清理长期未使用的卷
    cleanup_unused_volumes(max_age_days=7)
    
    # 2. 检查每个AZ的卷数量
    ensure_minimum_volumes_per_az(min_count=2)
    
    # 3. 更新缓存内容
    update_cache_content_if_needed()
    
    # 4. 创建快照备份
    create_cache_snapshots()
```

## 5. Spot实例Agent设计

### 5.1 Auto Scaling Group配置
```yaml
AutoScalingGroup:
  MinSize: 0
  MaxSize: 10
  DesiredCapacity: 2
  AvailabilityZones: 
    - us-east-1a
    - us-east-1b  
    - us-east-1c
  MixedInstancesPolicy:
    InstancesDistribution:
      OnDemandPercentage: 0
      SpotAllocationStrategy: diversified
    LaunchTemplate:
      LaunchTemplateSpecification:
        LaunchTemplateId: !Ref SpotAgentLaunchTemplate
        Version: $Latest
      Overrides:
        - InstanceType: c5.2xlarge
        - InstanceType: c5.4xlarge
        - InstanceType: m5.2xlarge
        - InstanceType: m5.4xlarge
        - InstanceType: r5.2xlarge
```

### 5.2 启动模板配置
```yaml
LaunchTemplate:
  ImageId: ami-xxxxxxxxx  # 预装Unity的自定义AMI
  SecurityGroupIds:
    - !Ref AgentSecurityGroup
  IamInstanceProfile: !Ref AgentInstanceProfile
  UserData: !Base64
    Fn::Sub: |
      #!/bin/bash
      # 1. 获取实例元数据
      INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
      AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)
      
      # 2. 调用Lambda分配缓存卷
      VOLUME_ID=$(aws lambda invoke \
        --function-name AllocateCacheVolume \
        --payload "{\"availability_zone\":\"$AZ\",\"project_id\":\"unity-game\"}" \
        --output text --query 'Payload' | jq -r '.volume_id')
      
      # 3. 挂载缓存卷
      aws ec2 attach-volume --volume-id $VOLUME_ID --instance-id $INSTANCE_ID --device /dev/xvdf
      
      # 4. 等待挂载完成并挂载文件系统
      while [ ! -e /dev/xvdf ]; do sleep 1; done
      mkdir -p /mnt/cache-volume
      mount /dev/xvdf /mnt/cache-volume
      
      # 5. 设置环境变量
      export UNITY_PROJECT_PATH=/mnt/cache-volume/unity-projects
      export GIT_CACHE_PATH=/mnt/cache-volume/git-repos
      
      # 6. 启动Jenkins Agent
      java -jar /opt/jenkins/agent.jar \
        -jnlpUrl ${JenkinsURL}/computer/${AgentName}/slave-agent.jnlp \
        -secret ${AgentSecret} \
        -workDir /mnt/cache-volume/workspace
      
      # 7. 设置Spot中断处理
      nohup /opt/scripts/spot-interruption-handler.sh &
```

### 5.3 Spot中断处理
```bash
#!/bin/bash
# spot-interruption-handler.sh

while true; do
  # 检查Spot中断通知
  if curl -s http://169.254.169.254/latest/meta-data/spot/instance-action 2>/dev/null; then
    echo "$(date): Spot interruption detected"
    
    # 1. 通知Jenkins停止当前构建
    curl -X POST "${JENKINS_URL}/computer/${AGENT_NAME}/doDisconnect" \
      --user "${JENKINS_USER}:${JENKINS_TOKEN}"
    
    # 2. 等待当前任务完成或超时
    sleep 30
    
    # 3. 卸载缓存卷
    umount /mnt/cache-volume
    
    # 4. 调用Lambda回收缓存卷
    aws lambda invoke \
      --function-name ReleaseCacheVolume \
      --payload "{\"volume_id\":\"${VOLUME_ID}\",\"instance_id\":\"${INSTANCE_ID}\"}" \
      /tmp/release-response.json
    
    echo "$(date): Cache volume released, instance shutting down"
    break
  fi
  sleep 5
done
```

## 6. 数据存储设计

### 6.1 DynamoDB缓存池状态表
```yaml
TableName: jenkins-cache-pool-status
PartitionKey: VolumeId (String)
Attributes:
  - VolumeId: String          # EBS卷ID
  - Status: String            # Available/InUse/Building/Maintenance
  - AvailabilityZone: String  # 可用区
  - LastUsed: Number          # 最后使用时间戳
  - ProjectId: String         # 项目标识
  - CacheVersion: String      # 缓存版本
  - CreatedTime: Number       # 创建时间
  - InstanceId: String        # 当前使用的实例ID (仅InUse状态)

GlobalSecondaryIndexes:
  - IndexName: AZ-Status-Index
    PartitionKey: AvailabilityZone
    SortKey: Status
  - IndexName: Project-Status-Index  
    PartitionKey: ProjectId
    SortKey: Status
```

### 6.2 S3存储桶设计
```yaml
构建产物存储桶:
  BucketName: jenkins-unity-build-artifacts
  Structure:
    ├── builds/
    │   └── [project-name]/
    │       └── [build-number]/
    │           ├── artifacts/
    │           └── logs/
    ├── cache-templates/
    │   └── [project-name]/
    │       └── cache-snapshot-[version].tar.gz
    └── backups/
        └── jenkins-config/
```

### 6.3 EFS文件系统
```yaml
Jenkins数据存储:
  FileSystemId: fs-xxxxxxxxx
  PerformanceMode: generalPurpose
  ThroughputMode: provisioned
  ProvisionedThroughputInMibps: 100
  MountTargets:
    - SubnetId: !Ref PrivateSubnet1a
      SecurityGroups: [!Ref EFSSecurityGroup]
    - SubnetId: !Ref PrivateSubnet1b  
      SecurityGroups: [!Ref EFSSecurityGroup]
    - SubnetId: !Ref PrivateSubnet1c
      SecurityGroups: [!Ref EFSSecurityGroup]
```

## 7. 监控和运维设计

### 7.1 CloudWatch监控指标
```yaml
自定义指标:
  - CachePool/AvailableVolumes    # 可用缓存卷数量
  - CachePool/InUseVolumes        # 使用中缓存卷数量
  - CachePool/BuildingVolumes     # 构建中缓存卷数量
  - SpotInstances/RunningCount    # 运行中Spot实例数量
  - SpotInstances/InterruptionRate # Spot中断率
  - Jenkins/ActiveBuilds          # 活跃构建数量
  - Jenkins/QueueLength           # 构建队列长度

系统指标:
  - EC2实例CPU、内存、磁盘使用率
  - EFS吞吐量和IOPS
  - EBS卷IOPS和吞吐量
  - ALB请求数量和延迟
```

### 7.2 告警配置
```yaml
关键告警:
  - Jenkins Master实例状态异常
  - 可用缓存卷数量低于阈值 (< 2个)
  - Spot实例中断率过高 (> 50%)
  - 构建队列长度过长 (> 10)
  - EFS吞吐量达到限制
  - 构建失败率过高 (> 20%)

通知方式:
  - SNS主题推送
  - 邮件通知
  - Slack集成 (可选)
```

### 7.3 日志管理
```yaml
日志收集:
  - Jenkins系统日志 → CloudWatch Logs
  - 构建日志 → S3 + CloudWatch Logs
  - Spot实例系统日志 → CloudWatch Logs
  - Lambda函数日志 → CloudWatch Logs
  - ALB访问日志 → S3

日志保留策略:
  - 系统日志: 30天
  - 构建日志: 90天
  - 访问日志: 7天
```

## 8. 安全设计

### 8.1 IAM角色和策略
```yaml
Jenkins Master Role:
  Policies:
    - EC2管理权限 (启动/停止Spot实例)
    - EFS访问权限
    - S3读写权限 (构建产物)
    - CloudWatch日志写入权限
    - Lambda调用权限 (缓存池管理)

Agent Instance Role:
  Policies:
    - EBS卷attach/detach权限
    - S3读写权限 (构建产物)
    - CloudWatch日志写入权限
    - Lambda调用权限 (缓存池管理)
    - EC2元数据访问权限

Lambda Execution Role:
  Policies:
    - DynamoDB读写权限
    - EC2卷管理权限
    - CloudWatch日志写入权限
```

### 8.2 网络安全
- Jenkins Master部署在公有子网，通过严格安全组控制访问
- 所有Agent实例部署在私有子网
- 使用NAT Gateway为私有子网提供出站互联网访问
- 安全组严格限制端口访问
- EFS和DynamoDB使用VPC端点访问
- ALB提供HTTPS终止和Web访问
- SSH访问开放给所有IP，依赖密钥认证和系统安全

### 8.3 数据加密
- EBS卷启用静态加密
- EFS启用传输和静态加密
- S3存储桶启用服务端加密
- DynamoDB启用静态加密

## 9. 成本优化

### 9.1 成本估算
```yaml
月度成本估算 (us-east-1):
  Jenkins Master:
    - c5.large On-Demand: ~$52/月
    - 公网IP: 免费 (实例运行时)
  
  Spot Agents (平均2个实例运行):
    - c5.2xlarge Spot (90% off): ~$25/月
    - 数据传输: ~$10/月
  
  存储:
    - EFS (100GB): ~$30/月
    - EBS缓存池 (9个100GB卷): ~$90/月
    - S3存储: ~$20/月
  
  其他服务:
    - DynamoDB: ~$5/月
    - CloudWatch: ~$10/月
    - ALB: ~$20/月
  
  总计: ~$261/月
  
对比传统On-Demand方案节省: ~60%
```

### 9.2 成本优化策略
- 使用Spot实例降低计算成本
- EBS卷使用gp3类型优化性能价格比
- 定期清理未使用的缓存卷
- 构建产物使用S3 Intelligent Tiering
- 监控资源使用情况，动态调整容量

## 10. 部署和维护

### 10.1 部署顺序
1. **基础设施部署**
   - VPC和网络组件
   - 安全组和IAM角色
   - EFS文件系统
   - DynamoDB表

2. **Jenkins Master部署**
   - EC2实例启动
   - Jenkins安装和配置
   - EFS挂载和数据迁移
   - ALB配置

3. **缓存池系统部署**
   - Lambda函数部署
   - 初始缓存卷创建
   - DynamoDB数据初始化

4. **AMI构建和Spot Agent配置**
   - Jenkins Master AMI构建
   - Unity Agent AMI构建
   - Launch Template创建
   - Auto Scaling Group配置

5. **监控和告警配置**
   - CloudWatch Dashboard
   - 告警规则配置
   - SNS通知设置

### 10.2 日常维护任务
- 监控缓存池状态，确保足够的可用卷
- 定期更新Unity Editor和构建工具
- 检查Spot实例中断率和成本效益
- 备份Jenkins配置和重要数据
- 更新安全补丁和系统组件

### 10.3 故障恢复
- Jenkins Master故障: Auto Scaling Group自动替换
- EFS故障: AWS托管服务自动恢复
- 缓存卷故障: 从快照恢复或重新初始化
- Spot实例中断: 自动启动新实例并分配缓存卷

## 11. AMI构建和软件准备方案

### 11.1 Jenkins Master AMI构建

#### 11.1.1 基础AMI选择
- **基础镜像**: Amazon Linux 2023 (最新稳定版)
- **架构**: x86_64
- **实例类型**: c5.large (构建时使用)

#### 11.1.2 Jenkins Master软件栈
```bash
#!/bin/bash
# jenkins-master-setup.sh

# 1. 系统更新和基础软件安装
sudo dnf update -y
sudo dnf install -y java-17-amazon-corretto-devel git wget curl unzip

# 2. Jenkins安装
wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key
sudo dnf install -y jenkins

# 3. Jenkins配置
sudo systemctl enable jenkins
sudo mkdir -p /var/lib/jenkins/init.groovy.d

# 4. 安装AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 5. 安装Docker (用于构建和管理)
sudo dnf install -y docker
sudo systemctl enable docker
sudo usermod -a -G docker jenkins

# 6. 创建EFS挂载点
sudo mkdir -p /var/lib/jenkins
sudo chown jenkins:jenkins /var/lib/jenkins

# 7. 安装EFS工具
sudo dnf install -y amazon-efs-utils

# 8. Jenkins插件预安装脚本
cat > /var/lib/jenkins/plugins.txt << 'EOF'
ant:latest
build-timeout:latest
credentials-binding:latest
email-ext:latest
git:latest
github-branch-source:latest
gradle:latest
ldap:latest
mailer:latest
matrix-auth:latest
pam-auth:latest
pipeline-github-lib:latest
pipeline-stage-view:latest
ssh-slaves:latest
timestamper:latest
workflow-aggregator:latest
ws-cleanup:latest
ec2:latest
unity3d-plugin:latest
blueocean:latest
configuration-as-code:latest
EOF

# 9. Jenkins初始化配置
cat > /var/lib/jenkins/jenkins.yaml << 'EOF'
jenkins:
  systemMessage: "Unity CI/CD Jenkins Master"
  numExecutors: 2
  mode: NORMAL
  scmCheckoutRetryCount: 3
  
  clouds:
    - ec2:
        name: "unity-agents"
        region: "us-east-1"
        useInstanceProfileForCredentials: true
        
security:
  globalJobDslSecurityConfiguration:
    useScriptSecurity: false
    
unclassified:
  location:
    adminAddress: "admin@company.com"
    url: "https://jenkins.company.com/"
EOF

# 10. 启动脚本
cat > /opt/jenkins-startup.sh << 'EOF'
#!/bin/bash
# 挂载EFS
echo "fs-xxxxxxxxx.efs.us-east-1.amazonaws.com:/ /var/lib/jenkins efs defaults,_netdev" >> /etc/fstab
mount -a

# 确保权限正确
chown -R jenkins:jenkins /var/lib/jenkins

# 启动Jenkins
systemctl start jenkins
EOF

chmod +x /opt/jenkins-startup.sh

# 11. 清理
sudo dnf clean all
sudo rm -rf /tmp/* /var/tmp/*
```

### 11.2 Unity Agent AMI构建

#### 11.2.1 Unity Agent软件栈
```bash
#!/bin/bash
# unity-agent-setup.sh

# 1. 系统更新和基础软件
sudo dnf update -y
sudo dnf install -y java-17-amazon-corretto-devel git wget curl unzip xvfb

# 2. 安装Unity Hub和Unity Editor
# Unity Hub安装
wget -qO - https://hub.unity3d.com/linux/keys/public | sudo apt-key add -
echo 'deb https://hub.unity3d.com/linux/repos/deb stable main' | sudo tee /etc/apt/sources.list.d/unityhub.list
sudo apt update
sudo apt install -y unityhub

# 创建Unity安装目录
sudo mkdir -p /opt/unity
sudo chown ec2-user:ec2-user /opt/unity

# Unity Editor安装脚本 (需要根据具体版本调整)
cat > /opt/install-unity.sh << 'EOF'
#!/bin/bash
# Unity Editor 2023.2.x LTS安装
UNITY_VERSION="2023.2.20f1"
UNITY_CHANGESET="0e25a174756c"

# 下载Unity Editor
wget -O unity-editor.tar.xz "https://download.unity3d.com/download_unity/${UNITY_CHANGESET}/LinuxEditorInstaller/Unity.tar.xz"

# 解压到指定目录
sudo tar -xf unity-editor.tar.xz -C /opt/unity/

# 创建符号链接
sudo ln -sf /opt/unity/Editor/Unity /usr/local/bin/unity

# 清理安装文件
rm unity-editor.tar.xz
EOF

chmod +x /opt/install-unity.sh
/opt/install-unity.sh

# 3. 安装构建工具
# Git LFS
curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.rpm.sh | sudo bash
sudo dnf install -y git-lfs
git lfs install

# Node.js (用于某些构建工具)
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo dnf install -y nodejs

# 4. 安装AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 5. Jenkins Agent安装
wget https://repo.jenkins-ci.org/public/org/jenkins-ci/main/remoting/4.13/remoting-4.13.jar -O /opt/jenkins-agent.jar

# 6. 创建缓存目录结构
sudo mkdir -p /mnt/cache-volume
sudo mkdir -p /opt/unity-cache
sudo mkdir -p /opt/build-tools

# 7. 安装Android SDK (如果需要Android构建)
wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O android-tools.zip
unzip android-tools.zip -d /opt/android-sdk
export ANDROID_HOME=/opt/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin

# 接受Android SDK许可
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-33" "build-tools;33.0.0"

# 8. 环境变量配置
cat > /etc/environment << 'EOF'
UNITY_PATH=/opt/unity/Editor/Unity
ANDROID_HOME=/opt/android-sdk
JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/unity/Editor:/opt/android-sdk/platform-tools
EOF

# 9. Unity许可证配置脚本
cat > /opt/setup-unity-license.sh << 'EOF'
#!/bin/bash
# Unity许可证激活 (需要根据实际情况配置)
# 这里使用Unity Personal License作为示例

# 从AWS Systems Manager Parameter Store获取许可证信息
UNITY_USERNAME=$(aws ssm get-parameter --name "/jenkins/unity/username" --with-decryption --query 'Parameter.Value' --output text)
UNITY_PASSWORD=$(aws ssm get-parameter --name "/jenkins/unity/password" --with-decryption --query 'Parameter.Value' --output text)
UNITY_SERIAL=$(aws ssm get-parameter --name "/jenkins/unity/serial" --with-decryption --query 'Parameter.Value' --output text)

# 激活Unity许可证
/opt/unity/Editor/Unity -batchmode -quit -logFile /var/log/unity-activation.log -username "$UNITY_USERNAME" -password "$UNITY_PASSWORD" -serial "$UNITY_SERIAL"
EOF

chmod +x /opt/setup-unity-license.sh

# 10. Agent启动脚本
cat > /opt/jenkins-agent-startup.sh << 'EOF'
#!/bin/bash

# 获取实例元数据
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)

# 设置Agent名称
AGENT_NAME="unity-agent-${INSTANCE_ID}"

# 分配缓存卷
VOLUME_ID=$(aws lambda invoke \
  --function-name AllocateCacheVolume \
  --payload "{\"availability_zone\":\"$AZ\",\"project_id\":\"unity-game\"}" \
  --output text --query 'Payload' | jq -r '.volume_id')

# 挂载缓存卷
aws ec2 attach-volume --volume-id $VOLUME_ID --instance-id $INSTANCE_ID --device /dev/xvdf

# 等待挂载完成
while [ ! -e /dev/xvdf ]; do sleep 1; done

# 检查文件系统
if ! blkid /dev/xvdf; then
    # 如果是新卷，创建文件系统
    mkfs.ext4 /dev/xvdf
fi

# 挂载缓存卷
mount /dev/xvdf /mnt/cache-volume

# 创建必要的目录结构
mkdir -p /mnt/cache-volume/unity-projects
mkdir -p /mnt/cache-volume/git-repos
mkdir -p /mnt/cache-volume/unity-cache
mkdir -p /mnt/cache-volume/build-tools
mkdir -p /mnt/cache-volume/workspace
mkdir -p /mnt/cache-volume/dependencies

# 设置Unity缓存目录
export UNITY_CACHE_PATH=/mnt/cache-volume/unity-cache

# 激活Unity许可证
/opt/setup-unity-license.sh

# 获取Jenkins连接信息
JENKINS_URL=$(aws ssm get-parameter --name "/jenkins/master/url" --query 'Parameter.Value' --output text)
AGENT_SECRET=$(aws ssm get-parameter --name "/jenkins/agent/secret" --with-decryption --query 'Parameter.Value' --output text)

# 启动Jenkins Agent
java -jar /opt/jenkins-agent.jar \
  -jnlpUrl "${JENKINS_URL}/computer/${AGENT_NAME}/slave-agent.jnlp" \
  -secret "${AGENT_SECRET}" \
  -workDir /mnt/cache-volume/workspace \
  -name "${AGENT_NAME}" &

# 启动Spot中断处理
nohup /opt/spot-interruption-handler.sh &

# 保存重要变量供其他脚本使用
echo "VOLUME_ID=$VOLUME_ID" > /tmp/agent-vars
echo "INSTANCE_ID=$INSTANCE_ID" >> /tmp/agent-vars
echo "AGENT_NAME=$AGENT_NAME" >> /tmp/agent-vars
EOF

chmod +x /opt/jenkins-agent-startup.sh

# 11. Spot中断处理脚本
cat > /opt/spot-interruption-handler.sh << 'EOF'
#!/bin/bash

# 加载变量
source /tmp/agent-vars

while true; do
  if curl -s http://169.254.169.254/latest/meta-data/spot/instance-action 2>/dev/null; then
    echo "$(date): Spot interruption detected"
    
    # 停止Jenkins Agent
    pkill -f jenkins-agent.jar
    
    # 等待任务完成
    sleep 30
    
    # 卸载缓存卷
    umount /mnt/cache-volume
    
    # 回收缓存卷
    aws lambda invoke \
      --function-name ReleaseCacheVolume \
      --payload "{\"volume_id\":\"${VOLUME_ID}\",\"instance_id\":\"${INSTANCE_ID}\"}" \
      /tmp/release-response.json
    
    echo "$(date): Cache volume released, shutting down"
    break
  fi
  sleep 5
done
EOF

chmod +x /opt/spot-interruption-handler.sh

# 12. 系统服务配置
cat > /etc/systemd/system/jenkins-agent.service << 'EOF'
[Unit]
Description=Jenkins Unity Agent
After=network.target

[Service]
Type=forking
User=ec2-user
ExecStart=/opt/jenkins-agent-startup.sh
Restart=no

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable jenkins-agent

# 13. 清理
sudo dnf clean all
sudo rm -rf /tmp/* /var/tmp/*
```

### 11.3 AMI构建流程

#### 11.3.1 使用Packer构建AMI
```json
{
  "variables": {
    "aws_region": "us-east-1",
    "source_ami": "ami-0abcdef1234567890",
    "instance_type": "c5.large"
  },
  "builders": [
    {
      "type": "amazon-ebs",
      "region": "{{user `aws_region`}}",
      "source_ami": "{{user `source_ami`}}",
      "instance_type": "{{user `instance_type`}}",
      "ssh_username": "ec2-user",
      "ami_name": "jenkins-master-{{timestamp}}",
      "ami_description": "Jenkins Master with Unity CI/CD tools",
      "tags": {
        "Name": "Jenkins Master AMI",
        "Environment": "Production",
        "Project": "Unity-CICD"
      }
    }
  ],
  "provisioners": [
    {
      "type": "shell",
      "script": "jenkins-master-setup.sh"
    }
  ]
}
```

#### 11.3.2 Unity Agent AMI构建配置
```json
{
  "variables": {
    "aws_region": "us-east-1",
    "source_ami": "ami-0abcdef1234567890",
    "instance_type": "c5.2xlarge"
  },
  "builders": [
    {
      "type": "amazon-ebs",
      "region": "{{user `aws_region`}}",
      "source_ami": "{{user `source_ami`}}",
      "instance_type": "{{user `instance_type`}}",
      "ssh_username": "ec2-user",
      "ami_name": "unity-agent-{{timestamp}}",
      "ami_description": "Unity Build Agent with Unity Editor and tools",
      "ebs_optimized": true,
      "tags": {
        "Name": "Unity Agent AMI",
        "Environment": "Production",
        "Project": "Unity-CICD"
      }
    }
  ],
  "provisioners": [
    {
      "type": "shell",
      "script": "unity-agent-setup.sh"
    }
  ]
}
```

### 11.4 软件版本管理

#### 11.4.1 版本固定策略
```yaml
软件版本清单:
  操作系统: Amazon Linux 2023 (固定版本)
  Java: Amazon Corretto 17 (LTS)
  Jenkins: 2.426.x (LTS)
  Unity Editor: 2023.2.20f1 (LTS)
  Android SDK: API Level 33
  Git: 最新稳定版
  AWS CLI: v2最新版
  
更新策略:
  - 每月检查安全更新
  - 每季度更新Unity Editor版本
  - Jenkins插件每月更新
  - 操作系统补丁每周检查
```

#### 11.4.2 Unity许可证管理
```bash
# Unity许可证存储在AWS Systems Manager Parameter Store
# 加密存储，仅授权实例可访问

# 存储许可证信息
aws ssm put-parameter \
  --name "/jenkins/unity/username" \
  --value "your-unity-username" \
  --type "SecureString"

aws ssm put-parameter \
  --name "/jenkins/unity/password" \
  --value "your-unity-password" \
  --type "SecureString"

aws ssm put-parameter \
  --name "/jenkins/unity/serial" \
  --value "your-unity-serial" \
  --type "SecureString"
```

### 11.5 AMI维护和更新

#### 11.5.1 自动化AMI构建流程

**构建方式: 提供完整的自动化脚本**

我们将提供以下自动化工具:

1. **一键式构建脚本**
```bash
#!/bin/bash
# build-amis.sh - 一键式构建AMI

# 设置变量
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"

echo "Building AMIs with prefix: $PROJECT_PREFIX"

# 构建Jenkins Master AMI
echo "Building Jenkins Master AMI..."
packer build \
  -var "project_prefix=$PROJECT_PREFIX" \
  -var "aws_region=$AWS_REGION" \
  jenkins-master.pkr.hcl

# 构建Unity Agent AMI
echo "Building Unity Agent AMI..."
packer build \
  -var "project_prefix=$PROJECT_PREFIX" \
  -var "aws_region=$AWS_REGION" \
  -var "unity_version=$UNITY_VERSION" \
  unity-agent.pkr.hcl

echo "AMI build completed!"
```

2. **CodeBuild自动化构建**
```yaml
# buildspec.yml - CodeBuild配置
version: 0.2
env:
  variables:
    PROJECT_PREFIX: "unity-cicd"
    AWS_DEFAULT_REGION: "us-east-1"
    UNITY_VERSION: "2023.2.20f1"
phases:
  install:
    runtime-versions:
      python: 3.9
    commands:
      - echo Installing Packer...
      - wget https://releases.hashicorp.com/packer/1.9.4/packer_1.9.4_linux_amd64.zip
      - unzip packer_1.9.4_linux_amd64.zip
      - mv packer /usr/local/bin/
      - packer version
  pre_build:
    commands:
      - echo Validating Packer templates...
      - packer validate jenkins-master.pkr.hcl
      - packer validate unity-agent.pkr.hcl
  build:
    commands:
      - echo Build started on `date`
      - echo "Building AMIs with prefix: $PROJECT_PREFIX"
      - ./build-amis.sh
  post_build:
    commands:
      - echo Build completed on `date`
      - echo "AMIs built successfully with prefix: $PROJECT_PREFIX"
artifacts:
  files:
    - ami-ids.json
    - build-log.txt
```

3. **GitHub Actions自动化**
```yaml
# .github/workflows/build-amis.yml
name: Build AMIs
on:
  push:
    paths:
      - 'ami-scripts/**'
      - 'packer/**'
  workflow_dispatch:
    inputs:
      project_prefix:
        description: 'Project prefix for resource naming'
        required: true
        default: 'unity-cicd'
      unity_version:
        description: 'Unity version to install'
        required: true
        default: '2023.2.20f1'

jobs:
  build-amis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Install Packer
        run: |
          wget https://releases.hashicorp.com/packer/1.9.4/packer_1.9.4_linux_amd64.zip
          unzip packer_1.9.4_linux_amd64.zip
          sudo mv packer /usr/local/bin/
      - name: Build AMIs
        env:
          PROJECT_PREFIX: ${{ github.event.inputs.project_prefix || 'unity-cicd' }}
          UNITY_VERSION: ${{ github.event.inputs.unity_version || '2023.2.20f1' }}
        run: ./build-amis.sh
```

#### 11.5.2 AMI测试验证
```bash
#!/bin/bash
# ami-validation.sh

# 1. 启动测试实例
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $NEW_AMI_ID \
  --instance-type c5.large \
  --key-name test-key \
  --security-group-ids sg-xxxxxxxxx \
  --subnet-id subnet-xxxxxxxxx \
  --query 'Instances[0].InstanceId' \
  --output text)

# 2. 等待实例启动
aws ec2 wait instance-running --instance-ids $INSTANCE_ID

# 3. 运行验证测试
# - Jenkins服务状态检查
# - Unity Editor版本验证
# - 必需插件检查
# - 网络连接测试

# 4. 清理测试实例
aws ec2 terminate-instances --instance-ids $INSTANCE_ID
```

## 12. 技术风险和缓解措施

### 11.1 主要风险
1. **Spot实例大规模中断**
   - 缓解: 多样化实例类型，跨多个AZ部署
   - 备选: 关键构建使用On-Demand实例

2. **EBS卷管理复杂性**
   - 缓解: 完善的状态管理和监控
   - 备选: 简化为EFS共享存储方案

3. **缓存数据一致性**
   - 缓解: 严格的卷分配和回收流程
   - 备选: 定期重建缓存卷

4. **网络分区或AZ故障**
   - 缓解: 多AZ部署，自动故障转移
   - 备选: 跨Region备份方案

### 11.2 性能风险
1. **EFS性能瓶颈**
   - 缓解: 使用Provisioned Throughput模式
   - 监控: 实时监控IOPS和吞吐量

2. **EBS卷IOPS限制**
   - 缓解: 使用gp3卷类型，配置足够IOPS
   - 优化: 根据实际使用情况调整配置

## 13. 资源命名规范和自定义配置

### 13.1 自定义前缀支持

**设计目标**: 支持用户自定义资源命名前缀，避免资源冲突

#### 13.1.1 命名规则
```yaml
资源命名模式:
  基础格式: "{project_prefix}-{resource_type}-{identifier}"
  示例: "unity-cicd-jenkins-master"
  
参数说明:
  project_prefix: 用户自定义前缀 (默认: "unity-cicd")
  resource_type: 资源类型 (vpc, ec2, efs, s3等)
  identifier: 资源标识符 (master, agent, cache等)
```

#### 13.1.2 CDK参数化配置
```python
# cdk_app.py - CDK应用主文件
from aws_cdk import App, Environment
from constructs import Construct
from jenkins_unity_stack import JenkinsUnityStack

class JenkinsUnityApp(Construct):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # 从环境变量或参数获取配置
        project_prefix = self.node.try_get_context("project_prefix") or "unity-cicd"
        aws_region = self.node.try_get_context("aws_region") or "us-east-1"
        unity_version = self.node.try_get_context("unity_version") or "2023.2.20f1"
        
        # 创建主栈
        JenkinsUnityStack(
            self, f"{project_prefix}-stack",
            project_prefix=project_prefix,
            unity_version=unity_version,
            env=Environment(region=aws_region)
        )

app = App()
JenkinsUnityApp(app, "jenkins-unity-app")
app.synth()
```

#### 13.1.3 资源命名映射表
```yaml
# 资源命名映射 (project_prefix = "my-game")
AWS资源类型:
  VPC: "my-game-vpc"
  子网:
    - "my-game-public-subnet-1a"
    - "my-game-private-subnet-1a"
  安全组:
    - "my-game-jenkins-master-sg"
    - "my-game-jenkins-agent-sg"
    - "my-game-alb-sg"
  EC2实例:
    - "my-game-jenkins-master"
  ALB: "my-game-jenkins-alb"
  EFS: "my-game-jenkins-efs"
  DynamoDB: "my-game-cache-pool-status"
  Lambda函数:
    - "my-game-allocate-cache-volume"
    - "my-game-release-cache-volume"
  IAM角色:
    - "my-game-jenkins-master-role"
    - "my-game-jenkins-agent-role"
  CloudWatch日志组:
    - "my-game-jenkins-logs"
    - "my-game-agent-logs"
```

#### 13.1.4 S3存储桶命名策略
```python
# S3存储桶命名策略 - 避免全局冲突
def generate_s3_bucket_name(project_prefix: str, bucket_type: str, aws_account_id: str, aws_region: str) -> str:
    """
    生成唯一的S3存储桶名称
    """
    # 使用账户ID和区域确保唯一性
    unique_suffix = f"{aws_account_id}-{aws_region}"
    bucket_name = f"{project_prefix}-{bucket_type}-{unique_suffix}"
    
    # 确保符合S3命名规则
    bucket_name = bucket_name.lower().replace("_", "-")
    
    return bucket_name

# 示例使用
project_prefix = "my-game"
aws_account_id = "123456789012"
aws_region = "us-east-1"

bucket_names = {
    "artifacts": generate_s3_bucket_name(project_prefix, "build-artifacts", aws_account_id, aws_region),
    "cache_templates": generate_s3_bucket_name(project_prefix, "cache-templates", aws_account_id, aws_region),
    "logs": generate_s3_bucket_name(project_prefix, "logs", aws_account_id, aws_region)
}

# 结果:
# my-game-build-artifacts-123456789012-us-east-1
# my-game-cache-templates-123456789012-us-east-1
# my-game-logs-123456789012-us-east-1
```

#### 13.1.5 部署命令示例
```bash
# 1. 使用默认配置部署
cdk deploy

# 2. 使用自定义前缀部署
cdk deploy -c project_prefix="my-game" -c aws_region="us-west-2"

# 3. 使用配置文件
cdk deploy -c project_prefix="production-unity" -c unity_version="2023.3.0f1"

# 4. 环境变量方式
export PROJECT_PREFIX="staging-game"
export AWS_REGION="eu-west-1"
export UNITY_VERSION="2023.2.20f1"
cdk deploy
```

#### 13.1.6 配置文件支持
```json
// cdk.json - CDK配置文件
{
  "app": "python cdk_app.py",
  "context": {
    "project_prefix": "unity-cicd",
    "aws_region": "us-east-1",
    "unity_version": "2023.2.20f1",
    "jenkins_instance_type": "c5.large",
    "agent_instance_types": ["c5.2xlarge", "c5.4xlarge", "m5.2xlarge"],
    "cache_volume_size": 100,
    "min_cache_volumes_per_az": 2,
    "max_spot_agents": 10
  }
}
```

```yaml
# config/production.yaml - 环境特定配置
project_prefix: "prod-unity-cicd"
aws_region: "us-east-1"
unity_version: "2023.2.20f1"

jenkins:
  instance_type: "c5.xlarge"
  volume_size: 50

agents:
  instance_types:
    - "c5.4xlarge"
    - "m5.4xlarge"
    - "r5.2xlarge"
  max_instances: 20
  
cache:
  volume_size: 200
  min_volumes_per_az: 3
  
monitoring:
  enable_detailed_monitoring: true
  log_retention_days: 90
```

### 13.2 部署脚本示例
```bash
#!/bin/bash
# deploy.sh - 一键式部署脚本

set -e

# 默认参数
PROJECT_PREFIX="${PROJECT_PREFIX:-unity-cicd}"
AWS_REGION="${AWS_REGION:-us-east-1}"
UNITY_VERSION="${UNITY_VERSION:-2023.2.20f1}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

echo "Deploying Jenkins Unity CI/CD with following configuration:"
echo "  Project Prefix: $PROJECT_PREFIX"
echo "  AWS Region: $AWS_REGION"
echo "  Unity Version: $UNITY_VERSION"
echo "  Environment: $ENVIRONMENT"

# 检查依赖
command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required"; exit 1; }
command -v cdk >/dev/null 2>&1 || { echo "AWS CDK is required"; exit 1; }

# 获取AWS账户信息
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "  AWS Account: $AWS_ACCOUNT_ID"

# 部署CDK栈
echo "Deploying CDK stack..."
cdk deploy \
  -c project_prefix="$PROJECT_PREFIX" \
  -c aws_region="$AWS_REGION" \
  -c unity_version="$UNITY_VERSION" \
  -c environment="$ENVIRONMENT" \
  --require-approval never

echo "Deployment completed successfully!"
echo "Jenkins URL will be available at: https://$PROJECT_PREFIX-jenkins-alb-$AWS_ACCOUNT_ID.$AWS_REGION.elb.amazonaws.com"
```

## 14. 扩展性考虑

### 12.1 水平扩展
- 支持多个Unity项目并行构建
- 缓存池可按项目分组管理
- Agent实例可根据负载自动扩缩容

### 12.2 功能扩展
- 支持其他游戏引擎 (Unreal Engine等)
- 集成代码质量检查工具
- 添加构建产物分发功能
- 支持多环境部署流水线

---

**文档版本**: 1.0  
**创建日期**: 2024-01-15  
**最后更新**: 2024-01-15  
**审核状态**: 待审核