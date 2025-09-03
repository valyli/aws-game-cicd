# Jenkins EC2 Plugin 实现计划

## 项目概述

将当前的固定 ASG Agent 架构迁移到 Jenkins EC2 Plugin 动态 Agent 管理模式，实现真正的云原生 CI/CD 系统。

## 项目目标

### 主要目标
1. **消除手动操作**: 实现完全自动化的 Agent 管理
2. **降低成本**: 使用 Spot 实例和按需创建，降低 60-90% 成本
3. **提高可靠性**: 每个任务使用独立的全新环境
4. **简化运维**: 零维护的动态扩缩容

### 保留内容
- Jenkins Master 的 CDK 自动化部署
- VPC、安全组等基础设施
- 现有的构建流程和 Jenkinsfile

## 详细实施计划

### 阶段 1: 项目结构搭建 (第 1 周)

#### 1.1 创建新项目结构
```
jenkins-plugin-cdk/
├── app.py                          # CDK 应用入口
├── cdk.json                        # CDK 配置
├── requirements.txt                # Python 依赖
├── stacks/
│   ├── __init__.py
│   ├── vpc_stack.py               # VPC 配置（复用现有）
│   ├── iam_stack.py               # IAM 角色配置
│   ├── jenkins_master_stack.py    # Master 部署（改进版）
│   ├── jenkins_plugin_stack.py    # EC2 Plugin 配置
│   └── agent_ami_stack.py         # AMI 构建和管理
├── configs/
│   ├── jenkins.yaml               # JCasC 配置
│   ├── ec2-plugin-config.yaml     # Plugin 详细配置
│   └── plugins.txt                # Jenkins 插件列表
├── scripts/
│   ├── build-agent-ami.sh         # AMI 构建脚本
│   ├── configure-plugin.sh        # Plugin 配置脚本
│   └── agent-init.sh              # Agent 初始化脚本
└── templates/
    ├── agent-userdata.sh          # Agent 用户数据模板
    └── jenkins-config.groovy      # Jenkins 配置模板
```

#### 1.2 基础配置文件
**cdk.json**:
```json
{
  "app": "python3 app.py",
  "watch": {
    "include": ["**"],
    "exclude": ["README.md", "cdk*.json", "requirements*.txt", "source.bat", "**/__pycache__", "**/*.pyc"]
  },
  "context": {
    "@aws-cdk/aws-lambda:recognizeLayerVersion": true,
    "@aws-cdk/core:checkSecretUsage": true,
    "@aws-cdk/core:target-partitions": ["aws", "aws-cn"]
  }
}
```

**requirements.txt**:
```
aws-cdk-lib>=2.100.0
constructs>=10.0.0
boto3>=1.26.0
pyyaml>=6.0
```

#### 1.3 任务清单
- [ ] 创建项目目录结构
- [ ] 设置 CDK 基础配置
- [ ] 复制并改进现有的 VPC/IAM 配置
- [ ] 创建基础的 Stack 类框架

### 阶段 2: Jenkins Master 改进 (第 1-2 周)

#### 2.1 Master Stack 增强
```python
class JenkinsMasterStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # 保留现有功能
        self._create_jenkins_master()
        self._create_alb()
        
        # 新增功能
        self._configure_ec2_plugin()
        self._setup_jcasc()
        self._create_ssm_parameters()
```

#### 2.2 JCasC 配置集成
**configs/jenkins.yaml**:
```yaml
jenkins:
  systemMessage: "Unity CI/CD Jenkins Master with EC2 Plugin"
  numExecutors: 0  # Master 不执行构建任务
  mode: EXCLUSIVE
  
  clouds:
    - ec2:
        name: "unity-build-cloud"
        region: "${AWS_REGION}"
        useInstanceProfileForCredentials: true
        instanceCapStr: "10"
        templates:
          - ami: "${UNITY_AGENT_AMI}"
            description: "Unity Build Agent"
            instanceType: "c5.large"
            securityGroups: "${AGENT_SECURITY_GROUP}"
            subnetId: "${PRIVATE_SUBNET_ID}"
            type: SPOT
            spotConfig:
              spotMaxBidPrice: "0.10"
            labelString: "unity linux build"
            mode: EXCLUSIVE
            numExecutors: 2
            remoteFS: "/opt/jenkins"
            idleTerminationMinutes: "10"
            initScript: |
              #!/bin/bash
              echo "Initializing Unity Build Agent"
            userData: |
              #!/bin/bash
              /opt/jenkins/agent-init.sh

security:
  globalJobDslSecurityConfiguration:
    useScriptSecurity: false

unclassified:
  location:
    adminAddress: "admin@company.com"
    url: "${JENKINS_URL}"
```

#### 2.3 任务清单
- [ ] 改进 Jenkins Master 部署脚本
- [ ] 集成 JCasC 配置
- [ ] 添加 EC2 Plugin 预配置
- [ ] 创建必要的 SSM 参数存储

### 阶段 3: Agent AMI 构建 (第 2 周)

#### 3.1 AMI 构建 Stack
```python
class AgentAmiStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # AMI 构建实例
        self._create_build_instance()
        
        # AMI 构建流水线
        self._create_ami_pipeline()
        
        # AMI 版本管理
        self._create_ami_versioning()
```

#### 3.2 Agent 初始化脚本
**scripts/agent-init.sh**:
```bash
#!/bin/bash
set -e

echo "Starting Unity Build Agent initialization..."

# 获取 Jenkins Master 信息
JENKINS_URL=$(aws ssm get-parameter --name "/jenkins/master/url" --region ${AWS_REGION} --query 'Parameter.Value' --output text)
JENKINS_SECRET=$(aws ssm get-parameter --name "/jenkins/agent/secret" --region ${AWS_REGION} --with-decryption --query 'Parameter.Value' --output text)

# 等待 Jenkins Master 可用
echo "Waiting for Jenkins Master at $JENKINS_URL"
for i in {1..30}; do
    if curl -s "$JENKINS_URL/login" > /dev/null; then
        echo "Jenkins Master is ready"
        break
    fi
    echo "Attempt $i/30: Jenkins not ready, waiting..."
    sleep 10
done

# Agent 连接由 EC2 Plugin 自动处理
echo "Agent initialization completed"
```

#### 3.3 AMI 构建脚本
**scripts/build-agent-ami.sh**:
```bash
#!/bin/bash
set -e

echo "Building Unity Agent AMI..."

# 1. 启动基础实例
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id ami-0abcdef1234567890 \
    --instance-type t3.medium \
    --key-name $KEY_NAME \
    --security-group-ids $SECURITY_GROUP \
    --subnet-id $SUBNET_ID \
    --iam-instance-profile Name=$IAM_ROLE \
    --user-data file://agent-setup.sh \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "Launched instance: $INSTANCE_ID"

# 2. 等待实例就绪
aws ec2 wait instance-running --instance-ids $INSTANCE_ID

# 3. 等待软件安装完成
echo "Waiting for software installation..."
sleep 600  # 10 minutes

# 4. 创建 AMI
AMI_ID=$(aws ec2 create-image \
    --instance-id $INSTANCE_ID \
    --name "unity-build-agent-$(date +%Y%m%d-%H%M%S)" \
    --description "Unity Build Agent AMI with Java, Unity, Docker" \
    --no-reboot \
    --query 'ImageId' \
    --output text)

echo "Created AMI: $AMI_ID"

# 5. 更新 SSM 参数
aws ssm put-parameter \
    --name "/jenkins/agent/ami-id" \
    --value $AMI_ID \
    --type String \
    --overwrite

# 6. 清理实例
aws ec2 terminate-instances --instance-ids $INSTANCE_ID

echo "AMI build completed: $AMI_ID"
```

#### 3.4 任务清单
- [ ] 设计 AMI 构建流程
- [ ] 创建 Agent 初始化脚本
- [ ] 实现 AMI 自动构建
- [ ] 测试 AMI 启动和连接

### 阶段 4: EC2 Plugin 配置 (第 2-3 周)

#### 4.1 Plugin 配置 Stack
```python
class JenkinsPluginStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # EC2 Plugin 配置
        self._create_plugin_config()
        
        # 监控和告警
        self._create_monitoring()
        
        # 成本控制
        self._create_cost_controls()
```

#### 4.2 详细 Plugin 配置
**configs/ec2-plugin-config.yaml**:
```yaml
ec2_cloud:
  name: "unity-build-cloud"
  region: "us-east-1"
  use_instance_profile: true
  instance_cap: 10
  
  templates:
    - name: "unity-agent-c5-large"
      ami: "${UNITY_AGENT_AMI}"
      instance_type: "c5.large"
      security_groups: ["${AGENT_SECURITY_GROUP}"]
      subnet_id: "${PRIVATE_SUBNET_ID}"
      
      # Spot 配置
      use_spot: true
      spot_max_bid: "0.10"
      
      # 标签和执行器
      labels: "unity linux build c5-large"
      mode: "EXCLUSIVE"
      num_executors: 2
      
      # 生命周期
      idle_termination_minutes: 10
      init_script: |
        #!/bin/bash
        echo "Initializing c5.large Unity Agent"
      
      # 用户数据
      user_data: |
        #!/bin/bash
        /opt/jenkins/agent-init.sh
    
    - name: "unity-agent-c5-xlarge"
      ami: "${UNITY_AGENT_AMI}"
      instance_type: "c5.xlarge"
      security_groups: ["${AGENT_SECURITY_GROUP}"]
      subnet_id: "${PRIVATE_SUBNET_ID}"
      
      use_spot: true
      spot_max_bid: "0.20"
      
      labels: "unity linux build c5-xlarge heavy"
      mode: "EXCLUSIVE"
      num_executors: 4
      
      idle_termination_minutes: 10
```

#### 4.3 任务清单
- [ ] 实现 EC2 Plugin 配置生成
- [ ] 创建多种实例类型模板
- [ ] 配置 Spot 实例支持
- [ ] 设置监控和告警

### 阶段 5: 集成测试 (第 3 周)

#### 5.1 测试环境部署
```bash
#!/bin/bash
# deploy-test-env.sh

echo "Deploying test environment..."

# 1. 部署基础设施
cd jenkins-plugin-cdk
cdk deploy --all --require-approval never

# 2. 构建 Agent AMI
./scripts/build-agent-ami.sh

# 3. 配置 Jenkins Plugin
./scripts/configure-plugin.sh

# 4. 运行测试
./scripts/run-integration-tests.sh
```

#### 5.2 测试用例
1. **基本功能测试**
   - [ ] Agent 自动创建
   - [ ] Agent 自动连接
   - [ ] 构建任务执行
   - [ ] Agent 自动销毁

2. **扩缩容测试**
   - [ ] 多任务并发执行
   - [ ] 自动扩容到多个 Agent
   - [ ] 任务完成后自动缩容

3. **故障恢复测试**
   - [ ] Agent 实例故障处理
   - [ ] Spot 实例中断处理
   - [ ] 网络故障恢复

4. **性能测试**
   - [ ] Agent 启动时间
   - [ ] 构建性能对比
   - [ ] 资源利用率

#### 5.3 任务清单
- [ ] 部署测试环境
- [ ] 执行功能测试
- [ ] 性能基准测试
- [ ] 故障恢复测试

### 阶段 6: 生产部署 (第 4 周)

#### 6.1 生产环境准备
```bash
#!/bin/bash
# prepare-production.sh

echo "Preparing production deployment..."

# 1. 备份当前配置
./scripts/backup-current-config.sh

# 2. 创建回滚计划
./scripts/create-rollback-plan.sh

# 3. 部署生产环境
cd jenkins-plugin-cdk
cdk deploy --all --require-approval never --context env=production

# 4. 验证部署
./scripts/verify-production-deployment.sh
```

#### 6.2 迁移策略
1. **蓝绿部署**
   - 保持现有系统运行
   - 部署新系统并行测试
   - 逐步切换流量

2. **渐进式迁移**
   - 先迁移非关键任务
   - 监控性能和稳定性
   - 逐步迁移所有任务

3. **回滚准备**
   - 保留旧系统配置
   - 准备快速回滚脚本
   - 监控关键指标

#### 6.3 任务清单
- [ ] 准备生产环境
- [ ] 执行蓝绿部署
- [ ] 渐进式任务迁移
- [ ] 监控和优化

## 成功标准

### 功能标准
- [ ] 完全消除手动操作
- [ ] Agent 自动创建和销毁
- [ ] 构建任务正常执行
- [ ] 支持并发多个 Agent

### 性能标准
- [ ] Agent 启动时间 < 5 分钟
- [ ] 构建性能与现有方案相当
- [ ] 系统可用性 > 99.5%

### 成本标准
- [ ] Agent 成本降低 > 60%
- [ ] 总体 TCO 降低 > 40%
- [ ] 资源利用率 > 80%

## 风险管理

### 主要风险
1. **技术风险**: Plugin 稳定性、AMI 构建失败
2. **性能风险**: Agent 启动时间过长
3. **成本风险**: Spot 实例可用性
4. **运维风险**: 新系统学习成本

### 缓解措施
1. **充分测试**: 完整的测试覆盖
2. **渐进迁移**: 分阶段降低风险
3. **监控告警**: 实时监控关键指标
4. **回滚计划**: 快速回滚能力

## 项目时间线

### 第 1 周 (当前周)
- [x] 完成方案分析和计划制定
- [ ] 创建项目结构
- [ ] 设置基础配置

### 第 2 周
- [ ] 完成 Jenkins Master 改进
- [ ] 实现 AMI 构建流程
- [ ] 开始 Plugin 配置

### 第 3 周
- [ ] 完成 Plugin 配置
- [ ] 集成测试
- [ ] 性能优化

### 第 4 周
- [ ] 生产环境部署
- [ ] 任务迁移
- [ ] 监控和优化

## 下一步行动

### 立即执行 (今天)
1. 创建 `jenkins-plugin-cdk` 项目结构
2. 设置基础的 CDK 配置
3. 开始 Jenkins Master Stack 改进

### 本周完成
1. 完成项目基础架构
2. 实现 AMI 构建脚本
3. 开始 JCasC 配置

### 下周目标
1. 完成 EC2 Plugin 配置
2. 开始集成测试
3. 性能基准测试

这个计划将在 4 周内完成从固定 ASG 到动态 Plugin 的完整迁移，实现真正的云原生 Jenkins CI/CD 系统。