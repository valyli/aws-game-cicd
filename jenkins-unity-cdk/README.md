
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

📋 **详细部署说明请参考**: [部署指南 (DEPLOYMENT.md)](./DEPLOYMENT.md)

### 一键部署

```bash
git clone <repository-url>
cd jenkins-unity-cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/deploy-complete.sh
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

### Jenkins初始设置

**获取初始管理员密码**
```bash
cd jenkins-unity-cdk
./get-jenkins-password.sh
```

**初始化向导注意事项**

如果在插件安装步骤遇到"An error occurred: Forbidden"错误：
1. 选择"Select plugins to install"
2. 点击"None"跳过插件安装
3. 完成初始设置后再手动安装需要的插件

> 💡 这个错误是由于CSRF保护机制导致的，通常发生在页面停留时间过长时。跳过插件安装是最简单的解决方案。

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

1. **Jenkins初始化插件安装失败**
   - 错误："An error occurred: Forbidden"
   - 原因：CSRF保护机制阻止请求
   - 解决：跳过插件安装，完成设置后手动安装

2. **Jenkins无法访问**
   - 检查ALB健康检查状态
   - 确认安全组配置正确
   - 查看EC2实例日志

3. **Unity构建失败**
   - 检查Unity许可证配置
   - 确认AMI包含正确的Unity版本
   - 查看构建日志

4. **Spot实例频繁中断**
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
