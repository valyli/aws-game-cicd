# Unity CI/CD 快速开始指南

## 🎯 当前状态

✅ **已完成部署**
- Jenkins Master: 运行中
- Jenkins Agent ASG: 已配置
- Lambda缓存管理: 已部署
- Demo Unity项目: 已创建

## 🚀 快速验证Unity Agent

### 1. 配置Unity许可证（必需）

```bash
# 替换为您的Unity账户信息
aws ssm put-parameter --name "/jenkins/unity/username" --value "your-unity-username" --type "SecureString"
aws ssm put-parameter --name "/jenkins/unity/password" --value "your-unity-password" --type "SecureString"
aws ssm put-parameter --name "/jenkins/unity/serial" --value "your-unity-serial" --type "SecureString"
```

### 2. 访问Jenkins并完成设置

**Jenkins URL**: http://unity-cicd-jenkins-alb-1860412095.us-east-1.elb.amazonaws.com:8080

**获取初始密码**:
```bash
./get-jenkins-password.sh
```

**必需插件**:
- EC2 Plugin (用于动态Agent)
- Git Plugin
- Pipeline Plugin

### 3. 配置EC2 Cloud（关键步骤）

在Jenkins中配置EC2 Cloud来启动Unity Agent：

1. **Jenkins → Manage Jenkins → Configure System**
2. **滚动到"Cloud"部分，点击"Add a new cloud" → "Amazon EC2"**
3. **配置如下**:
   ```
   Name: unity-agents
   Amazon EC2 Credentials: (选择或添加AWS凭证)
   Region: us-east-1
   Use Instance Profile for Credentials: ✓
   ```

4. **添加AMI配置**:
   ```
   Description: Unity Linux Agent
   AMI ID: ami-0abcdef1234567890  # 需要Unity Agent AMI
   Instance Type: c5.large
   Security group names: unity-cicd-jenkins-agent-sg
   Remote user: ec2-user
   Labels: unity-linux
   Usage: Only build jobs with label expressions matching this node
   ```

### 4. 创建Jenkins Pipeline任务

1. **Jenkins首页 → New Item**
2. **名称**: `unity-demo-build`
3. **类型**: Pipeline
4. **Pipeline配置**:
   - Definition: `Pipeline script from SCM`
   - SCM: `Git`
   - Repository URL: `file:///path/to/demo-unity-project` (或您的Git仓库)
   - Branch: `*/master`
   - Script Path: `Jenkinsfile`

### 5. 测试Unity Agent

**方法1: 手动启动Agent测试**
```bash
./test-unity-agent.sh
```

**方法2: 触发Jenkins构建**
1. 点击"Build Now"
2. 观察Jenkins是否能启动Unity Agent
3. 查看构建日志

## 🔧 故障排除

### Agent无法启动

**检查ASG配置**:
```bash
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names unity-cicd-jenkins-agent-asg
```

**检查安全组**:
```bash
aws ec2 describe-security-groups --group-names unity-cicd-jenkins-agent-sg
```

### Unity许可证问题

**验证许可证配置**:
```bash
aws ssm get-parameters --names "/jenkins/unity/username" "/jenkins/unity/password" "/jenkins/unity/serial" --with-decryption
```

### 构建失败

**查看Unity日志**:
- Jenkins构建页面 → Console Output
- 查看归档的Unity日志文件

## 📊 监控和成本

### 查看运行中的Agent
```bash
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*unity-agent*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].{InstanceId:InstanceId,State:State.Name,LaunchTime:LaunchTime}'
```

### 成本控制
- Agent使用Spot实例，成本节省高达90%
- 构建完成后Agent自动终止
- 设置合理的ASG最大容量限制

## 🎮 Demo项目说明

创建的Demo项目包含：

**文件结构**:
```
demo-unity-project/
├── Assets/
│   ├── Scripts/HelloWorld.cs      # 简单C#脚本
│   └── Editor/BuildScript.cs     # Unity构建脚本
├── ProjectSettings/
│   └── ProjectVersion.txt        # Unity版本信息
└── Jenkinsfile                   # Pipeline配置
```

**构建目标**:
- Android APK
- Windows EXE

**Pipeline阶段**:
1. Checkout - 代码检出
2. Unity License - 许可证激活
3. Build Android - Android构建
4. Build Windows - Windows构建

## 🔄 完整工作流程

1. **开发者提交代码** → Git仓库
2. **Jenkins检测变更** → 触发Pipeline
3. **动态启动Agent** → Unity Agent实例
4. **Unity编译** → 生成APK/EXE
5. **归档构建产物** → Jenkins存储
6. **Agent自动终止** → 节省成本

## 📈 扩展功能

### 添加更多构建平台
修改`BuildScript.cs`添加iOS、WebGL等平台

### 集成自动化测试
添加Unity Test Runner到Pipeline

### 部署到应用商店
集成Google Play Console、App Store Connect

### 质量检查
添加代码质量扫描、安全检查

## 🆘 获取帮助

**查看详细文档**:
- [部署指南](./DEPLOYMENT.md)
- [Unity Demo指南](./UNITY_DEMO_GUIDE.md)

**常用命令**:
```bash
# 验证部署状态
./verify-unity-setup.sh

# 获取Jenkins密码
./get-jenkins-password.sh

# 测试Agent连接
./test-unity-agent.sh
```

**重要提醒**:
- 确保配置Unity许可证
- 检查EC2 Cloud配置
- 监控Spot实例成本
- 定期更新Unity版本

## 🎉 成功标志

当您看到以下情况时，说明Unity CI/CD已成功运行：

1. ✅ Jenkins能够启动Unity Agent实例
2. ✅ Unity许可证激活成功
3. ✅ Unity项目编译成功
4. ✅ 生成APK/EXE构建产物
5. ✅ Agent构建完成后自动终止

恭喜！您的Unity CI/CD流水线已经可以正常工作了！🚀