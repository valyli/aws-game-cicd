# Jenkins Agent Launch Templates 管理指南

## 概述
这套脚本提供了完整的Jenkins Agent自动化部署解决方案，支持Linux和Windows平台。

## 文件说明

### 核心脚本
- `linux-jnlp-agent-userdata.sh` - Linux Agent自动连接脚本
- `windows-jnlp-agent-userdata.ps1` - Windows Agent自动连接脚本
- `manage-launch-templates.py` - Launch Template管理工具

### 配置要求
在使用前，请确保以下配置正确：

1. **Jenkins API认证**：
   ```bash
   # 在脚本中更新这些值
   JENKINS_USER="valyli"  # 你的Jenkins用户名
   JENKINS_TOKEN="11e60bc68521d47c1f32944d4045590e25"  # 你的API Token
   ```

2. **AWS资源ID**：
   ```python
   # 在manage-launch-templates.py中更新
   'security_group_id': 'sg-0cae1c773589f67ba',
   'iam_instance_profile': 'unity-cicd-jenkins-agent-instance-profile',
   'subnet_id': 'subnet-02ac9ed0cfe66207b'
   ```

## 使用方法

### 1. 创建Launch Templates
```bash
# 创建所有平台的Launch Templates
python3 manage-launch-templates.py create

# 只创建Linux平台
python3 manage-launch-templates.py create --platform linux

# 只创建Windows平台  
python3 manage-launch-templates.py create --platform windows
```

### 2. 更新Launch Templates
```bash
# 更新Linux Launch Template（创建新版本）
python3 manage-launch-templates.py update --platform linux

# 更新Windows Launch Template
python3 manage-launch-templates.py update --platform windows
```

### 3. 查看Launch Templates
```bash
# 列出所有Jenkins相关的Launch Templates
python3 manage-launch-templates.py list
```

### 4. 启动Agent实例
```bash
# 启动1个Linux Agent
python3 manage-launch-templates.py launch --name jenkins-linux-agent-template

# 启动2个Windows Agent
python3 manage-launch-templates.py launch --name jenkins-windows-agent-template --count 2
```

### 5. 删除Launch Templates
```bash
# 删除指定的Launch Template
python3 manage-launch-templates.py delete --name jenkins-linux-agent-template
```

## 自动化流程

### Agent启动后的自动化步骤：
1. **安装Java** - 自动下载并安装OpenJDK 17
2. **等待Jenkins Master** - 检查Jenkins可用性
3. **下载Agent JAR** - 从Jenkins下载agent.jar
4. **创建Jenkins节点** - 通过API自动创建节点
5. **获取JNLP Secret** - 自动获取连接密钥
6. **启动Agent服务** - 创建系统服务持续运行
7. **自动重连** - 服务异常时自动重启

### 预期结果：
- **Linux节点名称**：`linux-agent-{instance-id}`
- **Windows节点名称**：`windows-agent-{instance-id}`
- **节点标签**：`linux auto` 或 `windows auto`
- **工作目录**：`/opt/jenkins` 或 `C:\jenkins`

## 故障排查

### 1. 检查实例日志
```bash
# Linux实例
aws ssm send-command --instance-ids i-xxxxxxxxx --document-name "AWS-RunShellScript" \
  --parameters commands='["tail -50 /var/log/jenkins-agent-setup.log"]'

# Windows实例  
aws ssm send-command --instance-ids i-xxxxxxxxx --document-name "AWS-RunPowerShellScript" \
  --parameters commands='["Get-Content C:\jenkins-agent-setup.log -Tail 50"]'
```

### 2. 检查服务状态
```bash
# Linux
aws ssm send-command --instance-ids i-xxxxxxxxx --document-name "AWS-RunShellScript" \
  --parameters commands='["systemctl status jenkins-agent"]'

# Windows
aws ssm send-command --instance-ids i-xxxxxxxxx --document-name "AWS-RunPowerShellScript" \
  --parameters commands='["Get-Service JenkinsAgent"]'
```

### 3. 常见问题
- **认证失败**：检查Jenkins用户名和API Token
- **网络连接**：确认安全组允许访问Jenkins Master
- **Java安装失败**：检查网络连接和下载权限
- **节点创建失败**：确认Jenkins API权限

## 扩展使用

### Auto Scaling Group集成
```bash
# 创建Auto Scaling Group使用Launch Template
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name jenkins-linux-agents \
  --launch-template LaunchTemplateName=jenkins-linux-agent-template \
  --min-size 0 --max-size 10 --desired-capacity 2 \
  --vpc-zone-identifier subnet-02ac9ed0cfe66207b
```

### Spot实例支持
在Launch Template中添加Spot实例配置以降低成本。

### 多AZ部署
配置多个子网ID支持跨AZ部署提高可用性。

## 安全建议

1. **定期轮换API Token**
2. **使用最小权限IAM角色**
3. **启用EBS加密**
4. **限制安全组访问范围**
5. **监控Agent连接状态**