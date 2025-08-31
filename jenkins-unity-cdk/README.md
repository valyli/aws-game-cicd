
# Jenkins Unity CI/CD Infrastructure

基于AWS CDK构建的完整Jenkins Unity CI/CD基础设施，支持Spot实例、EBS缓存池和自动扩缩容。

## 项目概述

这个项目提供了一个完整的Jenkins Unity CI/CD解决方案，包括：

- **VPC网络架构**: 3个AZ的公有/私有子网配置
- **Jenkins Master**: 高可用的Jenkins主节点，使用EFS持久化存储
- **Jenkins Agents**: 基于Spot实例的自动扩缩容构建节点
- **EBS缓存池**: 智能的Unity Library缓存管理系统
- **监控告警**: 完整的CloudWatch监控和SNS告警
- **AMI自动化**: Packer模板自动构建Jenkins和Unity AMI

## 架构特点

### 成本优化
- 100% Spot实例用于构建节点，成本节省高达90%
- 智能EBS缓存池，避免重复下载Unity资源
- 自动扩缩容，按需使用资源

### 高可用性
- 跨多个AZ部署
- Spot中断自动处理和恢复
- EFS共享存储确保数据持久化

### 安全性
- 私有子网部署构建节点
- IAM最小权限原则
- 加密存储和传输

## 快速开始

### 前置要求

1. **AWS CLI**: 已配置有效的AWS凭证
2. **AWS CDK**: 版本 2.x
3. **Python 3.8+**: 用于CDK应用
4. **Packer** (可选): 用于构建自定义AMI

### 一键部署

```bash
# 克隆项目
git clone <repository-url>
cd jenkins-unity-cdk

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 完整部署
./scripts/deploy-complete.sh
```

### 分阶段部署

如果需要分阶段部署，可以使用以下命令：

```bash
# 1. 部署基础设施
cdk deploy unity-cicd-vpc-stack unity-cicd-storage-stack unity-cicd-iam-stack

# 2. 部署Lambda函数
cdk deploy unity-cicd-lambda-stack

# 3. 部署Jenkins Master
cdk deploy unity-cicd-jenkins-master-stack

# 4. 部署Jenkins Agents
cdk deploy unity-cicd-jenkins-agent-stack

# 5. 部署监控
cdk deploy unity-cicd-monitoring-stack
```

## 配置说明

### 环境配置

主要配置文件位于 `config/` 目录：

- `default.yaml`: 默认配置
- `production.yaml`: 生产环境配置

可以通过环境变量或CDK上下文覆盖配置：

```bash
export PROJECT_PREFIX="my-unity-cicd"
export AWS_REGION="us-west-2"
export UNITY_VERSION="2023.3.0f1"

# 或使用CDK上下文
cdk deploy -c project_prefix="my-unity-cicd" -c aws_region="us-west-2"
```

### Unity许可证配置

部署完成后，需要在AWS Systems Manager Parameter Store中配置Unity许可证：

```bash
# 配置Unity许可证信息
aws ssm put-parameter --name "/jenkins/unity/username" --value "your-unity-username" --type "SecureString"
aws ssm put-parameter --name "/jenkins/unity/password" --value "your-unity-password" --type "SecureString"
aws ssm put-parameter --name "/jenkins/unity/serial" --value "your-unity-serial" --type "SecureString"
```

## AMI构建

### 自动构建AMI

```bash
# 构建Jenkins Master和Unity Agent AMI
./scripts/build-amis.sh
```

### 手动构建

```bash
# 构建Jenkins Master AMI
cd packer
packer build jenkins-master.pkr.hcl

# 构建Unity Agent AMI
packer build unity-agent.pkr.hcl
```

## 使用指南

### 访问Jenkins

部署完成后，可以通过以下方式访问Jenkins：

```bash
# 获取Jenkins URL
aws cloudformation describe-stacks \
  --stack-name unity-cicd-jenkins-master-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
  --output text
```

默认登录凭证：
- 用户名: `admin`
- 密码: `admin123`

### Unity项目配置

1. **添加构建脚本**: 将 `examples/BuildScript.cs` 复制到Unity项目的 `Assets/Editor/` 目录
2. **创建Jenkinsfile**: 使用 `examples/Jenkinsfile` 作为模板
3. **配置Git仓库**: 在Jenkins中配置项目的Git仓库

### 示例Pipeline

```groovy
pipeline {
    agent { label 'unity linux' }
    
    stages {
        stage('Build Android') {
            steps {
                sh '''${UNITY_PATH} -batchmode -quit \
                    -projectPath "${WORKSPACE}" \
                    -buildTarget Android \
                    -executeMethod BuildScript.BuildAndroid'''
            }
        }
    }
}
```

## 监控和告警

### CloudWatch Dashboard

部署完成后，可以访问CloudWatch Dashboard查看系统状态：

```bash
# 获取Dashboard URL
aws cloudformation describe-stacks \
  --stack-name unity-cicd-monitoring-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
  --output text
```

### 告警订阅

```bash
# 订阅SNS告警主题
aws sns subscribe \
  --topic-arn $(aws cloudformation describe-stacks \
    --stack-name unity-cicd-monitoring-stack \
    --query 'Stacks[0].Outputs[?OutputKey==`AlertsTopicArn`].OutputValue' \
    --output text) \
  --protocol email \
  --notification-endpoint your-email@company.com
```

## 成本优化

### Spot实例策略

- **多样化策略**: 跨多个实例类型和AZ分布
- **中断处理**: 自动保存缓存并优雅关闭
- **回退机制**: Spot不可用时自动使用按需实例

### 缓存池管理

- **智能分配**: 优先使用现有缓存卷
- **自动清理**: 定期清理长期未使用的卷
- **快照备份**: 定期创建快照防止数据丢失

## 故障排除

### 常见问题

1. **Jenkins无法访问**
   - 检查ALB健康检查状态
   - 确认安全组配置正确
   - 查看EC2实例日志

2. **Unity构建失败**
   - 检查Unity许可证配置
   - 确认AMI包含正确的Unity版本
   - 查看构建日志

3. **Spot实例频繁中断**
   - 调整实例类型组合
   - 增加按需实例比例
   - 检查区域Spot价格历史

### 日志查看

```bash
# 查看Lambda函数日志
aws logs tail /aws/lambda/unity-cicd-allocate-cache-volume --follow

# 查看Jenkins Master日志
aws logs tail /aws/jenkins/master/unity-cicd --follow

# 查看Jenkins Agent日志
aws logs tail /aws/jenkins/agents/unity-cicd --follow
```

## 项目结构

```
jenkins-unity-cdk/
├── app.py                          # CDK应用入口
├── requirements.txt                # Python依赖
├── cdk.json                       # CDK配置
├── config/                        # 配置文件
│   ├── default.yaml
│   └── production.yaml
├── stacks/                        # CDK栈
│   ├── vpc_stack.py              # VPC和网络
│   ├── storage_stack.py          # EFS, DynamoDB, S3
│   ├── iam_stack.py              # IAM角色和策略
│   ├── lambda_stack.py           # Lambda函数
│   ├── jenkins_master_stack.py   # Jenkins Master
│   ├── jenkins_agent_stack.py    # Jenkins Agent
│   └── monitoring_stack.py       # 监控和日志
├── lambda_functions/              # Lambda函数代码
│   ├── allocate_cache_volume/
│   ├── release_cache_volume/
│   └── maintain_cache_pool/
├── scripts/                       # 部署和管理脚本
│   ├── build-amis.sh
│   └── deploy-complete.sh
├── packer/                        # Packer模板
│   ├── jenkins-master.pkr.hcl
│   └── unity-agent.pkr.hcl
├── configs/                       # Jenkins配置
│   ├── jenkins.yaml              # JCasC配置
│   └── plugins.txt               # 插件列表
└── examples/                      # 示例文件
    ├── Jenkinsfile
    └── BuildScript.cs
```

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## 许可证

本项目采用MIT许可证，详见LICENSE文件。

## 支持

如有问题或建议，请创建Issue或联系维护团队。
