# 部署指南

本文档详细说明如何部署Jenkins Unity CI/CD基础设施。

## 前置要求

### 必需工具
1. **AWS CLI**: 已配置有效的AWS凭证
2. **AWS CDK**: 版本 2.x
3. **Python 3.8+**: 用于CDK应用
4. **Packer** (可选): 用于构建自定义AMI

### AWS权限要求
确保您的AWS凭证具有以下权限：
- EC2 (创建实例、安全组、VPC等)
- IAM (创建角色和策略)
- CloudFormation (创建和管理栈)
- EFS (创建文件系统)
- S3 (创建存储桶)
- Lambda (创建函数)
- CloudWatch (创建日志组和告警)

## 快速部署

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

如果需要更精细的控制，可以分阶段部署：

```bash
# 1. 部署基础设施 (VPC, 存储, IAM)
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

## Jenkins初始设置

### 1. 获取访问URL

```bash
# 获取Jenkins URL
aws cloudformation describe-stacks \
  --stack-name unity-cicd-jenkins-master-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
  --output text
```

### 2. 获取初始管理员密码

**方法1：使用便捷脚本**
```bash
cd jenkins-unity-cdk
./get-jenkins-password.sh
```

**方法2：手动获取**
```bash
# 获取Jenkins实例ID
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names unity-cicd-jenkins-master-asg \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
  --output text)

# 通过SSM获取密码
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cat /var/lib/jenkins/.jenkins/secrets/initialAdminPassword"]'

# 获取命令结果
aws ssm get-command-invocation \
  --command-id <COMMAND_ID> \
  --instance-id $INSTANCE_ID \
  --query 'StandardOutputContent' \
  --output text
```

### 3. Jenkins初始化向导

1. **解锁Jenkins**: 使用上面获取的密码
2. **插件安装**: 
   - 如果遇到"Forbidden"错误（CSRF保护问题），选择"Select plugins to install"
   - 点击"None"跳过插件安装
   - 完成初始设置后再手动安装需要的插件
3. **创建管理员用户**: 设置用户名和密码
4. **实例配置**: 确认Jenkins URL

### 4. 常见初始化问题

**CSRF保护错误**
- 症状：插件安装时显示"An error occurred: Forbidden"
- 解决：选择"Select plugins to install" → "None" → "Install"
- 原因：页面停留时间过长导致CSRF令牌过期

**网络连接问题**
- 检查安全组是否允许出站HTTPS流量
- 确认NAT网关配置正确

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

## 部署验证

### 检查部署状态

```bash
# 检查所有栈状态
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `unity-cicd`)].{Name:StackName,Status:StackStatus}'

# 检查Jenkins实例状态
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names unity-cicd-jenkins-master-asg \
  --query 'AutoScalingGroups[0].Instances[*].{InstanceId:InstanceId,State:LifecycleState,Health:HealthStatus}'
```

### 功能测试

1. **Jenkins访问测试**
   ```bash
   curl -I $(aws cloudformation describe-stacks \
     --stack-name unity-cicd-jenkins-master-stack \
     --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
     --output text):8080/login
   ```

2. **EFS挂载测试**
   ```bash
   aws ssm send-command \
     --instance-ids <JENKINS_INSTANCE_ID> \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["df -h /var/lib/jenkins"]'
   ```

## 清理资源

### 完整清理

```bash
# 删除所有栈（按依赖顺序）
cdk destroy unity-cicd-monitoring-stack
cdk destroy unity-cicd-jenkins-agent-stack
cdk destroy unity-cicd-jenkins-master-stack
cdk destroy unity-cicd-lambda-stack
cdk destroy unity-cicd-storage-stack
cdk destroy unity-cicd-iam-stack
cdk destroy unity-cicd-vpc-stack
```

### 保留数据清理

如果需要保留EFS数据：

```bash
# 仅删除计算资源
cdk destroy unity-cicd-monitoring-stack
cdk destroy unity-cicd-jenkins-agent-stack
cdk destroy unity-cicd-jenkins-master-stack
cdk destroy unity-cicd-lambda-stack

# 保留存储和网络资源
# unity-cicd-storage-stack
# unity-cicd-vpc-stack
# unity-cicd-iam-stack
```

## 故障排除

### 部署失败

1. **权限不足**
   - 检查AWS凭证权限
   - 确认IAM角色配置正确

2. **资源限制**
   - 检查账户服务限制
   - 确认区域资源可用性

3. **网络配置**
   - 验证VPC CIDR不冲突
   - 检查子网配置

### Jenkins启动失败

1. **查看用户数据日志**
   ```bash
   aws ssm send-command \
     --instance-ids <INSTANCE_ID> \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["tail -50 /var/log/user-data.log"]'
   ```

2. **检查Java安装**
   ```bash
   aws ssm send-command \
     --instance-ids <INSTANCE_ID> \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["java -version","which java"]'
   ```

3. **检查EFS挂载**
   ```bash
   aws ssm send-command \
     --instance-ids <INSTANCE_ID> \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["mount | grep jenkins","ls -la /var/lib/jenkins/"]'
   ```

## 高级配置

### 自定义配置

修改 `config/default.yaml` 或创建新的配置文件：

```yaml
project_prefix: "my-unity-cicd"
aws_region: "us-west-2"

jenkins_master:
  instance_type: "t3.medium"
  volume_size: 30

jenkins_agents:
  min_capacity: 0
  max_capacity: 10
  spot_percentage: 100
```

### 多环境部署

```bash
# 开发环境
cdk deploy --context environment=dev

# 生产环境
cdk deploy --context environment=prod
```

### 自定义AMI

如果需要使用自定义AMI：

1. 构建AMI
2. 更新配置文件中的AMI ID
3. 重新部署相关栈

## 监控和维护

### 设置监控告警

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

### 定期维护任务

1. **更新Jenkins插件**
2. **检查EFS使用情况**
3. **清理旧的构建缓存**
4. **更新Unity版本**
5. **检查安全补丁**

## 成本优化建议

1. **使用Spot实例**: 已默认配置100% Spot实例
2. **自动扩缩容**: 根据构建需求自动调整实例数量
3. **EBS缓存池**: 复用Unity Library缓存
4. **定期清理**: 删除不需要的资源和日志

## 安全最佳实践

1. **定期更新**: 保持Jenkins和插件最新版本
2. **访问控制**: 配置适当的IAM权限
3. **网络隔离**: 使用私有子网部署构建节点
4. **加密传输**: 启用HTTPS和EFS加密
5. **审计日志**: 启用CloudTrail记录API调用