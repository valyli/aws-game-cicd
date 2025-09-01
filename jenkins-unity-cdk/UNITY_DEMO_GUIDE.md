# Unity Agent验证和Demo指南

本指南详细说明如何验证Unity编译Agent并运行Demo项目。

## 快速开始

### 自动化设置

```bash
# 给脚本执行权限
chmod +x setup-unity-demo.sh

# 运行完整设置
./setup-unity-demo.sh
# 选择选项 6 (Full setup)
```

## 分步骤验证

### 1. 部署Jenkins Agent栈

```bash
# 部署Agent栈
cdk deploy unity-cicd-jenkins-agent-stack --require-approval never
```

验证部署：
```bash
aws cloudformation describe-stacks --stack-name unity-cicd-jenkins-agent-stack --query 'Stacks[0].StackStatus'
```

### 2. 配置Unity许可证

Unity Agent需要有效的Unity许可证才能进行编译。将许可证信息存储在AWS Parameter Store中：

```bash
# 配置Unity许可证
aws ssm put-parameter --name "/jenkins/unity/username" --value "your-unity-username" --type "SecureString"
aws ssm put-parameter --name "/jenkins/unity/password" --value "your-unity-password" --type "SecureString"
aws ssm put-parameter --name "/jenkins/unity/serial" --value "your-unity-serial" --type "SecureString"
```

验证配置：
```bash
aws ssm get-parameter --name "/jenkins/unity/username" --with-decryption --query 'Parameter.Value'
```

### 3. 安装必需的Jenkins插件

Jenkins需要以下插件来管理Unity Agent：

**必需插件列表：**
- `ec2` - AWS EC2插件，用于动态启动Agent
- `git` - Git源码管理
- `workflow-aggregator` - Pipeline插件套件
- `pipeline-stage-view` - Pipeline可视化
- `build-timeout` - 构建超时控制
- `timestamper` - 时间戳
- `ws-cleanup` - 工作空间清理

**手动安装方式：**
1. 访问Jenkins → Manage Jenkins → Manage Plugins
2. 在Available标签页搜索并安装上述插件
3. 重启Jenkins

**自动安装方式：**
```bash
./setup-unity-demo.sh
# 选择选项 3 (Install Jenkins plugins)
```

### 4. 配置EC2 Cloud

在Jenkins中配置EC2 Cloud来动态启动Unity Agent：

1. **访问配置页面**
   - Jenkins → Manage Jenkins → Configure System
   - 滚动到"Cloud"部分

2. **添加EC2 Cloud**
   - 点击"Add a new cloud" → "Amazon EC2"
   - Name: `unity-agents`
   - Amazon EC2 Credentials: 选择或添加AWS凭证

3. **配置EC2设置**
   ```
   Region: us-east-1 (或您的部署区域)
   EC2 Key Pair's Private Key: (留空，使用IAM角色)
   Use Instance Profile for Credentials: ✓
   ```

4. **添加AMI配置**
   - 点击"Add" → "EC2 AMI"
   - AMI ID: `ami-0abcdef1234567890` (Unity Agent AMI)
   - Instance Type: `c5.large`
   - Security group names: `unity-cicd-jenkins-agent-sg`
   - Remote user: `ec2-user`
   - Labels: `unity-linux`
   - Usage: `Only build jobs with label expressions matching this node`

### 5. 创建Demo Unity项目

运行脚本创建示例项目：
```bash
./setup-unity-demo.sh
# 选择选项 4 (Create demo Unity project)
```

这将创建包含以下内容的Demo项目：
- 基本Unity项目结构
- 简单的C#脚本
- 构建脚本 (Android/Windows)
- Jenkinsfile Pipeline配置

### 6. 创建Jenkins Pipeline任务

1. **创建新任务**
   - Jenkins首页 → New Item
   - 名称: `unity-demo-build`
   - 类型: Pipeline

2. **配置Pipeline**
   - Pipeline Definition: `Pipeline script from SCM`
   - SCM: `Git`
   - Repository URL: 您的Git仓库地址
   - Branch: `*/main`
   - Script Path: `Jenkinsfile`

3. **保存配置**

### 7. 验证Unity Agent

#### 检查Agent启动

触发构建后，检查Agent是否正确启动：

```bash
# 检查运行中的Agent实例
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*unity-agent*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].{InstanceId:InstanceId,State:State.Name,LaunchTime:LaunchTime}'
```

#### 测试Unity安装

```bash
# 获取Agent实例ID
AGENT_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*unity-agent*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

# 测试Unity版本
aws ssm send-command \
  --instance-ids $AGENT_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["/opt/unity/Editor/Unity -version"]'
```

#### 检查构建日志

在Jenkins任务中查看构建日志：
1. 点击构建号
2. 查看"Console Output"
3. 检查Unity编译输出

## 故障排除

### Agent启动失败

**症状**: Jenkins显示"All nodes of label 'unity-linux' are offline"

**解决方案**:
1. 检查EC2 Cloud配置
2. 验证AMI ID是否正确
3. 确认安全组允许SSH访问
4. 检查IAM权限

```bash
# 检查安全组规则
aws ec2 describe-security-groups \
  --group-names unity-cicd-jenkins-agent-sg \
  --query 'SecurityGroups[0].IpPermissions'
```

### Unity许可证问题

**症状**: Unity编译失败，提示许可证错误

**解决方案**:
1. 验证Parameter Store中的许可证信息
2. 确认Unity账户有效
3. 检查许可证是否支持批处理模式

```bash
# 验证许可证参数
aws ssm get-parameters \
  --names "/jenkins/unity/username" "/jenkins/unity/password" "/jenkins/unity/serial" \
  --with-decryption
```

### 编译超时

**症状**: Unity编译过程中超时

**解决方案**:
1. 增加Jenkins构建超时时间
2. 使用更大的实例类型
3. 优化Unity项目设置

### 网络连接问题

**症状**: Agent无法连接到Jenkins Master

**解决方案**:
1. 检查VPC和子网配置
2. 验证NAT网关设置
3. 确认安全组规则

```bash
# 检查VPC配置
aws ec2 describe-vpcs --filters "Name=tag:Name,Values=*unity-cicd*"
```

## 性能优化

### 实例类型选择

| 构建类型 | 推荐实例类型 | 说明 |
|---------|-------------|------|
| 小型项目 | c5.large | 2 vCPU, 4 GB RAM |
| 中型项目 | c5.xlarge | 4 vCPU, 8 GB RAM |
| 大型项目 | c5.2xlarge | 8 vCPU, 16 GB RAM |

### 缓存优化

1. **启用EBS缓存池**
   ```bash
   # 部署Lambda缓存管理
   cdk deploy unity-cicd-lambda-stack
   ```

2. **配置Unity缓存**
   - 在Jenkinsfile中添加缓存恢复步骤
   - 使用共享的Library缓存

### Spot实例配置

默认配置使用100% Spot实例以降低成本：

```yaml
# config/default.yaml
jenkins_agents:
  spot_percentage: 100
  spot_max_price: "0.50"  # 每小时最大价格
```

## 监控和日志

### CloudWatch监控

查看Agent相关指标：
```bash
# 获取监控Dashboard URL
aws cloudformation describe-stacks \
  --stack-name unity-cicd-monitoring-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
  --output text
```

### 日志查看

```bash
# 查看Agent启动日志
aws logs tail /aws/ec2/unity-agents --follow

# 查看Lambda缓存日志
aws logs tail /aws/lambda/unity-cicd-allocate-cache-volume --follow
```

## 扩展配置

### 多Unity版本支持

1. 构建包含多个Unity版本的AMI
2. 在Jenkins中配置不同的Agent标签
3. 在Jenkinsfile中指定Unity版本

### 自定义构建脚本

扩展BuildScript.cs以支持更多平台：

```csharp
public static void BuildiOS()
{
    string[] scenes = GetScenes();
    string buildPath = "Builds/iOS/";
    
    BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.iOS, BuildOptions.None);
}

public static void BuildWebGL()
{
    string[] scenes = GetScenes();
    string buildPath = "Builds/WebGL/";
    
    BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.WebGL, BuildOptions.None);
}
```

### 并行构建

配置多个Agent同时构建不同平台：

```groovy
pipeline {
    agent none
    
    stages {
        stage('Parallel Builds') {
            parallel {
                stage('Android') {
                    agent { label 'unity-linux' }
                    steps {
                        // Android构建步骤
                    }
                }
                stage('Windows') {
                    agent { label 'unity-windows' }
                    steps {
                        // Windows构建步骤
                    }
                }
            }
        }
    }
}
```

## 最佳实践

1. **版本控制**: 将Unity项目设置和构建脚本纳入版本控制
2. **缓存策略**: 合理使用Library缓存减少构建时间
3. **资源管理**: 设置合理的超时和资源限制
4. **安全性**: 定期更新AMI和Unity版本
5. **成本控制**: 监控Spot实例使用情况和成本

## 下一步

完成Unity Agent验证后，您可以：

1. **集成更多平台**: 添加iOS、WebGL等构建目标
2. **自动化测试**: 集成Unity Test Runner
3. **部署流水线**: 添加自动部署到应用商店
4. **质量检查**: 集成代码质量和安全扫描工具
5. **通知系统**: 配置构建结果通知