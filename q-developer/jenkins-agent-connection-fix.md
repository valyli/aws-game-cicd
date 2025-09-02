# Jenkins Agent 连接修复指南

## 问题概述

Jenkins Agent 无法连接到 Jenkins Master，主要问题包括：
1. Agent 使用公网 IP 连接 Master（网络不通）
2. Agent 无法获取 instance ID（IMDSv2 问题）
3. ALB 8080 端口监听器丢失
4. JNLP 连接需要正确的 secret 和配置
5. Java 安装失败导致 Agent 无法运行

## 修复步骤

### 1. 网络连接修复

**问题**：Agent 尝试连接 Master 的公网 IP，但 Agent 在私有子网无法访问公网。

**解决方案**：修改 Agent 脚本使用 Master 的私有 IP。

```bash
# 错误的连接方式
JENKINS_URL="http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080"

# 正确的连接方式
JENKINS_URL="http://10.0.0.66:8080"  # Master 私有 IP
```

### 2. IMDSv2 兼容性修复

**问题**：Agent 无法获取 instance ID，导致 Agent 名称为空。

**原因**：新 EC2 实例默认使用 IMDSv2，需要 token 认证。

**解决方案**：更新元数据获取方式。

```bash
# 错误的方式（IMDSv1）
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)

# 正确的方式（IMDSv2）
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -s)
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id)
```

### 3. ALB 监听器修复

**问题**：ALB 缺少 8080 端口监听器，导致外部无法访问 Jenkins。

**解决方案**：手动添加 8080 端口监听器。

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
```

### 4. Java 安装修复

**问题**：Agent 上 Java 安装失败，导致无法运行 agent.jar。

**原因**：
1. 包管理器冲突（curl 包冲突）
2. Java 安装验证不充分
3. 缺少必要的依赖包

**解决方案**：使用强制安装和充分验证。

```bash
# 解决包冲突问题
echo "Installing dependencies with conflict resolution..."
yum install -y git wget unzip htop amazon-efs-utils --allowerasing

# 安装 Java 并处理冲突
echo "Installing Java 17..."
yum install -y java-17-amazon-corretto --allowerasing

# 验证 Java 安装
echo "Verifying Java installation..."
if ! java -version 2>&1; then
    echo "ERROR: Java installation failed! Retrying..."
    yum remove -y java-17-amazon-corretto
    yum clean all
    yum install -y java-17-amazon-corretto --allowerasing
    
    if ! java -version 2>&1; then
        echo "CRITICAL: Java installation failed after retry!"
        exit 1
    fi
fi

# 设置 JAVA_HOME
JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:bin/java::")
export JAVA_HOME
echo "JAVA_HOME=$JAVA_HOME" >> /etc/environment
echo "Java installed successfully at $JAVA_HOME"

# 验证 Java 可用性
echo "Final Java verification:"
java -version
echo "JAVA_HOME: $JAVA_HOME"
```

### 5. 手动创建 Jenkins 节点

**问题**：自动节点创建失败，Agent 无法找到对应的 Jenkins 节点。

**原因**：
1. Jenkins 安全设置阻止匿名 API 访问
2. CSRF 保护需要认证 token
3. 自动节点创建脚本认证失败

**解决方案**：在 Jenkins Web UI 中手动创建节点。

#### 手动创建步骤：

1. **访问 Jenkins**：
   ```
   http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080
   ```

2. **登录 Jenkins**：
   - 用户名：`valyli`
   - 密码：`111111`

3. **创建新节点**：
   - 点击 "Manage Jenkins" → "Nodes" → "New Node"
   - 节点名称：`unity-agent-i-0dff55811201880ed` (使用实际的 instance ID)
   - 选择："Permanent Agent"
   - 点击 "Create"

4. **配置节点**：
   - **Remote root directory**: `/opt/jenkins` 或 `./jenkins-agent`
   - **Launch method**: "Launch inbound agents via Java Web Start"
   - **Labels**: `unity linux`
   - **Usage**: "Use this node as much as possible"
   - **# of executors**: `2`
   - 点击 "Save"

5. **获取连接信息**：
   创建节点后，Jenkins 会显示连接命令，类似：
   ```bash
   curl -sO http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/jnlpJars/agent.jar
   java -jar agent.jar -url http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/ -secret edfc464cb2f4958023997f8cb9b0d4a7b33d5b2c46e39aed5321543b3e020ed9 -name "unity-agent-i-0dff55811201880ed" -webSocket -workDir "/opt/jenkins"
   ```

### 6. JNLP 连接配置

**解决方案**：使用手动创建节点后获得的连接信息，但需要修改为内部 IP。

```bash
# 从 Jenkins 页面获取的命令（使用外部 ALB）
java -jar agent.jar \
  -url http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/ \
  -secret edfc464cb2f4958023997f8cb9b0d4a7b33d5b2c46e39aed5321543b3e020ed9 \
  -name "unity-agent-i-0dff55811201880ed" \
  -webSocket -workDir "/opt/jenkins"

# 修改为内部 IP 的正确命令
java -jar agent.jar \
  -url http://10.0.0.213:8080/ \
  -secret edfc464cb2f4958023997f8cb9b0d4a7b33d5b2c46e39aed5321543b3e020ed9 \
  -name "unity-agent-i-0dff55811201880ed" \
  -webSocket -workDir "/opt/jenkins"
```

**关键点**：
- 使用 Jenkins Master 的**私有 IP** (如 10.0.0.213) 而不是 ALB 地址
- 保持 secret 和节点名称不变
- 确保使用 `-webSocket` 参数

## 验证步骤

### 1. 验证 Java 安装
```bash
# 检查 Java 版本
java -version

# 检查 JAVA_HOME
echo $JAVA_HOME

# 测试 Java 运行
java -help | head -5
```

### 3. 验证网络连接
```bash
# 在 Agent 上测试连接 Master
curl -I http://10.0.0.213:8080/
```

### 4. 验证 IMDSv2
```bash
# 测试获取 instance ID
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -s)
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id)
echo "Instance ID: $INSTANCE_ID"
```

### 5. 验证 ALB 监听器
```bash
# 检查监听器
aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query 'Listeners[].[Port,Protocol]' --output table
```

### 7. 验证 Agent 连接
```bash
# 检查 Agent 进程
ps aux | grep java | grep agent

# 检查连接日志
tail -f /opt/jenkins/agent.log
```

## 成功标志

1. **Java 安装**：Agent 上 Java 正常工作，能运行 jar 文件
2. **网络连接**：Agent 能访问 Master 私有 IP
3. **元数据获取**：Agent 能正确获取 instance ID
4. **ALB 访问**：外部能通过 8080 端口访问 Jenkins
5. **节点创建**：Jenkins Web UI 中能看到对应的 Agent 节点
6. **Agent 连接**：Jenkins 显示 "Agent successfully connected and online"
7. **连接日志**：Jenkins 日志显示 "Inbound agent connected from [Agent IP]"

## 关键配置文件

### Agent 启动脚本关键部分
```bash
# 使用 IMDSv2 获取元数据
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -s)
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id)
AGENT_NAME="unity-agent-$INSTANCE_ID"

# 使用内部 IP 连接
JENKINS_URL="http://10.0.0.66:8080"  # 需要动态获取 Master 私有 IP

# 等待节点创建后连接
for i in $(seq 1 30); do
    if curl -s "$JENKINS_URL/computer/$AGENT_NAME/jenkins-agent.jnlp" | grep -q "<jnlp>"; then
        echo "Node $AGENT_NAME found in Jenkins"
        break
    fi
    echo "Waiting for node creation... attempt $i/30"
    sleep 10
done
```

## 注意事项

1. **Master 私有 IP 获取**：需要动态获取 Master 实例的私有 IP，不能硬编码
2. **节点创建时机**：Agent 启动时，对应的 Jenkins 节点必须已存在
3. **手动节点创建**：目前需要手动在 Jenkins 中创建节点，自动创建尚未完全解决
4. **节点名称匹配**：确保 Jenkins 中的节点名称与 Agent 脚本中的 AGENT_NAME 一致
5. **网络安全组**：确保 Agent 安全组允许访问 Master 的 8080 端口
6. **健康检查**：ALB 健康检查路径应设置为 `/login`，接受 200,403,404 状态码
7. **Secret 保存**：从 Jenkins 获取的 secret 是一次性的，需要在 Agent 脚本中正确使用

## 长期自动化改进建议

1. **动态 IP 发现**：Agent 应该能自动发现 Master 的私有 IP
2. **自动节点创建**：解决 Jenkins CSRF 和认证问题，实现自动节点创建
3. **连接重试机制**：Agent 应该有健壮的重试和错误处理机制
4. **监控告警**：添加 Agent 连接状态监控
5. **节点生命周期管理**：自动清理离线节点，自动注册新节点
6. **云原生架构迁移**：迁移到 Jenkins EC2 Plugin 动态 Agent 管理

## 手动操作步骤总结

### 当前部署需要的手动操作

#### 1. 手动修复 ALB 8080 监听器
**原因**：CDK 代码中有 8080 监听器配置，但部署时可能丢失

```bash
# 获取 ALB 和目标组 ARN
ALB_ARN=$(aws elbv2 describe-load-balancers --names unity-cicd-jenkins-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)
TG_ARN=$(aws elbv2 describe-target-groups --names unity-cicd-jenkins-tg --query 'TargetGroups[0].TargetGroupArn' --output text)

# 手动创建 8080 监听器
aws elbv2 create-listener --load-balancer-arn $ALB_ARN --protocol HTTP --port 8080 --default-actions Type=forward,TargetGroupArn=$TG_ARN
```

#### 2. 手动创建 Jenkins 节点
**原因**：Jenkins 安全设置阻止自动节点创建

**步骤**：
- 访问：`http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080`
- 登录：用户名 `valyli`，密码 `111111`
- 创建节点：
  - Manage Jenkins → Nodes → New Node
  - 节点名称：`unity-agent-{instance-id}` (使用实际的 instance ID)
  - 类型：Permanent Agent
  - 配置：Remote root directory `/opt/jenkins`，Launch method "Java Web Start"

#### 3. 手动执行 Agent 连接
**原因**：Agent 在私有子网，无法访问外部 ALB，需要使用内部 IP

```bash
# 使用从 Jenkins 获取的 secret，但修改为内部 IP
java -jar agent.jar -url http://10.0.0.213:8080/ -secret {从Jenkins获取的secret} -name "unity-agent-{instance-id}" -webSocket -workDir "/opt/jenkins"
```

### 为什么需要手动操作？

1. **ALB 监听器问题**：
   - CDK 部署过程中 8080 监听器配置可能丢失
   - 需要手动添加才能外部访问 Jenkins

2. **自动节点创建失败**：
   - Jenkins 安全设置阻止匿名 API 访问
   - CSRF 保护需要认证 token
   - 自动创建脚本无法通过认证

3. **网络连接问题**：
   - Agent 在私有子网，无法访问外部 ALB
   - 需要使用 Master 内部 IP 连接

### 自动化改进方向

根据 `jenkins-cloud-native-agent-architecture.md` 文档，未来应该：

1. **使用 Jenkins EC2 Plugin** 替代固定 ASG
2. **动态创建和销毁 Agent** 实现真正的云原生
3. **解决认证问题** 实现自动节点创建
4. **修复 ALB 配置** 确保监听器不丢失

**当前手动步骤是临时解决方案**，最终目标是实现完全自动化的云原生 Jenkins Agent 管理。

### 部署检查清单

每次部署后需要验证：

- [ ] ALB 8080 端口监听器存在
- [ ] Jenkins Master 可以外部访问
- [ ] Agent 实例成功启动
- [ ] Java 正确安装在 Agent 上
- [ ] Agent 能获取正确的 instance ID
- [ ] Jenkins 中手动创建对应节点
- [ ] Agent 成功连接到 Jenkins Master
- [ ] Agent 状态显示为 "Connected"

## 常见问题排查

### Agent 无法连接
1. 检查 Jenkins 中是否存在对应节点
2. 检查节点名称是否匹配
3. 检查 secret 是否正确
4. 检查网络连接（ping Master IP）

### Java 相关错误
1. 检查 Java 是否正确安装：`java -version`
2. 检查 JAVA_HOME 设置：`echo $JAVA_HOME`
3. 检查 agent.jar 是否下载成功

### 网络问题
1. 检查安全组配置
2. 检查 ALB 8080 端口监听器
3. 检查 Master 实例状态和 Jenkins 服务状态

### 手动操作失败
1. **ALB 监听器创建失败**：检查 ALB 和目标组是否存在
2. **Jenkins 节点创建失败**：检查用户权限和登录凭证
3. **Agent 连接失败**：检查 secret 是否正确，网络是否通畅