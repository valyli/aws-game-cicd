# Jenkins Agent 部署手动操作步骤

## 概述

当前 Jenkins Agent 部署需要以下手动操作步骤才能完成连接。这些步骤是临时解决方案，最终目标是实现完全自动化。

## 必需的手动操作

### 1. 修复 ALB 8080 监听器

**问题**：CDK 部署过程中 8080 端口监听器可能丢失，导致外部无法访问 Jenkins。

**操作步骤**：
```bash
# 获取 ALB 和目标组 ARN
ALB_ARN=$(aws elbv2 describe-load-balancers --names unity-cicd-jenkins-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)
TG_ARN=$(aws elbv2 describe-target-groups --names unity-cicd-jenkins-tg --query 'TargetGroups[0].TargetGroupArn' --output text)

# 创建 8080 监听器
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 8080 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

# 验证监听器创建成功
aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query 'Listeners[].[Port,Protocol]' --output table
```

**预期结果**：
```
-------------------
|DescribeListeners|
+-------+---------+
|  8080 |  HTTP   |
|  80   |  HTTP   |
+-------+---------+
```

### 2. 手动创建 Jenkins 节点

**问题**：Jenkins 安全设置阻止自动节点创建，需要手动在 Web UI 中创建。

**操作步骤**：

1. **访问 Jenkins**：
   ```
   http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080
   ```

2. **登录**：
   - 用户名：`valyli`
   - 密码：`111111`

3. **创建节点**：
   - 导航：Manage Jenkins → Nodes → New Node
   - 节点名称：`unity-agent-{instance-id}` (使用实际的 instance ID)
   - 选择：Permanent Agent
   - 点击：Create

4. **配置节点**：
   - **Name**: `unity-agent-{instance-id}`
   - **Description**: `Unity Build Agent - {instance-id}`
   - **# of executors**: `2`
   - **Remote root directory**: `/opt/jenkins`
   - **Labels**: `unity linux`
   - **Usage**: `Use this node as much as possible`
   - **Launch method**: `Launch inbound agents via Java Web Start`
   - **Availability**: `Keep this agent online as much as possible`

5. **保存并获取连接信息**：
   - 点击 Save
   - 记录显示的连接命令和 secret

**示例连接信息**：
```bash
curl -sO http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/jnlpJars/agent.jar
java -jar agent.jar -url http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/ -secret 1df4f082819e16ed37604e557cd90ae55e8c64d461e73332f35d97de37560b78 -name "unity-agent-i-0b01f9ffd7422c70b" -webSocket -workDir "/jenkins-agent"
```

### 3. 手动连接 Agent

**问题**：Agent 在私有子网无法访问外部 ALB，需要使用内部 IP 连接。

**操作步骤**：

1. **获取 Jenkins Master 私有 IP**：
   ```bash
   MASTER_IP=$(aws ec2 describe-instances \
     --filters "Name=tag:Name,Values=*jenkins-master*" "Name=instance-state-name,Values=running" \
     --query "Reservations[0].Instances[0].PrivateIpAddress" \
     --output text)
   echo "Master IP: $MASTER_IP"
   ```

2. **获取 Agent 实例 ID**：
   ```bash
   AGENT_INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
     --auto-scaling-group-names unity-cicd-jenkins-agent-asg \
     --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
     --output text)
   echo "Agent Instance: $AGENT_INSTANCE_ID"
   ```

3. **在 Agent 上执行连接命令**：
   ```bash
   # 使用 SSM 在 Agent 实例上执行
   aws ssm send-command \
     --instance-ids $AGENT_INSTANCE_ID \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=[
       "cd /opt/jenkins",
       "curl -sO http://'$MASTER_IP':8080/jnlpJars/agent.jar",
       "nohup java -jar agent.jar -url http://'$MASTER_IP':8080/ -secret {从Jenkins获取的secret} -name \"unity-agent-'$AGENT_INSTANCE_ID'\" -webSocket -workDir \"/opt/jenkins\" > agent.log 2>&1 &"
     ]'
   ```

4. **验证连接**：
   ```bash
   # 检查 Agent 进程
   aws ssm send-command \
     --instance-ids $AGENT_INSTANCE_ID \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["ps aux | grep java | grep agent","tail -5 /opt/jenkins/agent.log"]'
   ```

## 部署后验证清单

每次部署后必须验证以下项目：

### 基础设施验证
- [ ] ALB 8080 端口监听器存在
- [ ] Jenkins Master 可以外部访问
- [ ] Agent 实例成功启动
- [ ] Agent 实例可以通过 SSM 访问

### Agent 功能验证
- [ ] Java 正确安装在 Agent 上
- [ ] Agent 能获取正确的 instance ID (IMDSv2)
- [ ] Agent 能访问 Master 私有 IP
- [ ] agent.jar 成功下载

### Jenkins 集成验证
- [ ] Jenkins 中手动创建对应节点
- [ ] 节点名称与 Agent 实例 ID 匹配
- [ ] Agent 成功连接到 Jenkins Master
- [ ] Agent 状态显示为 "Connected"
- [ ] Jenkins 日志显示 "Inbound agent connected"

## 自动化脚本

为简化手动操作，可以使用以下脚本：

### 完整部署脚本
```bash
#!/bin/bash
# jenkins-agent-deploy.sh

set -e

echo "=== Jenkins Agent 部署脚本 ==="

# 1. 修复 ALB 监听器
echo "1. 修复 ALB 8080 监听器..."
ALB_ARN=$(aws elbv2 describe-load-balancers --names unity-cicd-jenkins-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)
TG_ARN=$(aws elbv2 describe-target-groups --names unity-cicd-jenkins-tg --query 'TargetGroups[0].TargetGroupArn' --output text)

# 检查监听器是否已存在
LISTENER_EXISTS=$(aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query 'Listeners[?Port==`8080`]' --output text)
if [ -z "$LISTENER_EXISTS" ]; then
    aws elbv2 create-listener --load-balancer-arn $ALB_ARN --protocol HTTP --port 8080 --default-actions Type=forward,TargetGroupArn=$TG_ARN
    echo "✅ 8080 监听器创建成功"
else
    echo "✅ 8080 监听器已存在"
fi

# 2. 获取实例信息
echo "2. 获取实例信息..."
MASTER_IP=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=*jenkins-master*" "Name=instance-state-name,Values=running" --query "Reservations[0].Instances[0].PrivateIpAddress" --output text)
AGENT_INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names unity-cicd-jenkins-agent-asg --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)

echo "Master IP: $MASTER_IP"
echo "Agent Instance: $AGENT_INSTANCE_ID"

# 3. 等待 Agent 启动完成
echo "3. 等待 Agent 启动完成..."
sleep 120

# 4. 验证 Java 安装
echo "4. 验证 Java 安装..."
aws ssm send-command --instance-ids $AGENT_INSTANCE_ID --document-name "AWS-RunShellScript" --parameters 'commands=["java -version"]' --query 'Command.CommandId' --output text

echo "=== 手动操作提醒 ==="
echo "请完成以下手动操作："
echo "1. 在 Jenkins Web UI 中创建节点: unity-agent-$AGENT_INSTANCE_ID"
echo "2. 获取连接 secret 并执行连接命令"
echo "3. 验证 Agent 连接状态"
echo ""
echo "Jenkins URL: http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080"
echo "登录: valyli / 111111"
```

## 故障排除

### 常见问题及解决方案

1. **ALB 监听器创建失败**
   - 检查 ALB 和目标组是否存在
   - 验证 AWS 权限
   - 检查是否已存在相同端口的监听器

2. **Jenkins 节点创建失败**
   - 验证登录凭证
   - 检查用户权限
   - 确认节点名称格式正确

3. **Agent 连接失败**
   - 验证 secret 是否正确
   - 检查网络连通性
   - 确认 Java 安装状态
   - 检查防火墙和安全组设置

4. **实例无法通过 SSM 访问**
   - 检查 SSM Agent 状态
   - 验证 IAM 角色权限
   - 确认实例在正确的子网中

## 未来改进计划

1. **短期改进**：
   - 创建自动化脚本减少手动操作
   - 添加更多验证和错误处理
   - 改进监控和日志记录

2. **长期目标**：
   - 迁移到 Jenkins EC2 Plugin
   - 实现完全自动化的动态 Agent 管理
   - 消除所有手动操作步骤

## 相关文档

- [Jenkins Agent 连接修复指南](jenkins-agent-connection-fix.md)
- [Jenkins 云原生架构设计](jenkins-cloud-native-agent-architecture.md)
- [手动节点创建指南](manual-node-creation-guide.md)