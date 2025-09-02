# Jenkins 手动节点创建指南

## 背景

由于 Jenkins 安全设置和 CSRF 保护，自动节点创建脚本无法正常工作。当前需要手动在 Jenkins Web UI 中创建节点。

## 手动创建步骤

### 1. 访问 Jenkins
```
http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080
```

### 2. 登录
- 用户名：`valyli`
- 密码：`111111`

### 3. 创建新节点
1. 点击 **"Manage Jenkins"**
2. 点击 **"Nodes"** 或 **"Manage Nodes and Clouds"**
3. 点击 **"New Node"**
4. 输入节点名称：`unity-agent-i-0dff55811201880ed` (使用实际的 instance ID)
5. 选择 **"Permanent Agent"**
6. 点击 **"Create"**

### 4. 配置节点
- **Name**: `unity-agent-i-0dff55811201880ed`
- **Description**: `Unity Build Agent - i-0dff55811201880ed`
- **# of executors**: `2`
- **Remote root directory**: `/opt/jenkins` 或 `./jenkins-agent`
- **Labels**: `unity linux`
- **Usage**: `Use this node as much as possible`
- **Launch method**: `Launch inbound agents via Java Web Start`
- **Availability**: `Keep this agent online as much as possible`

### 5. 保存配置
点击 **"Save"** 保存节点配置。

### 6. 获取连接信息
创建节点后，Jenkins 会显示连接命令，包含：
- Agent JAR 下载链接
- 连接 URL
- Secret token
- 节点名称

示例连接命令：
```bash
curl -sO http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/jnlpJars/agent.jar
java -jar agent.jar -url http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/ -secret edfc464cb2f4958023997f8cb9b0d4a7b33d5b2c46e39aed5321543b3e020ed9 -name "unity-agent-i-0dff55811201880ed" -webSocket -workDir "/opt/jenkins"
```

## 关键信息提取

从 Jenkins 页面获取以下信息：
1. **Secret**: `edfc464cb2f4958023997f8cb9b0d4a7b33d5b2c46e39aed5321543b3e020ed9`
2. **Node Name**: `unity-agent-i-0dff55811201880ed`
3. **Work Directory**: `/opt/jenkins`

## Agent 连接修改

Agent 需要使用内部 IP 而不是 ALB 地址：

```bash
# Jenkins 提供的命令（使用 ALB）
java -jar agent.jar -url http://unity-cicd-jenkins-alb-222129503.us-east-1.elb.amazonaws.com:8080/ -secret xxx -name "unity-agent-xxx" -webSocket -workDir "/opt/jenkins"

# 修改为内部 IP 的命令
java -jar agent.jar -url http://10.0.0.213:8080/ -secret xxx -name "unity-agent-xxx" -webSocket -workDir "/opt/jenkins"
```

## 验证节点创建

### 在 Jenkins Web UI 中验证
1. 访问 **"Manage Jenkins"** → **"Nodes"**
2. 应该能看到新创建的节点
3. 节点状态应该显示为 "Offline" (等待 Agent 连接)

### 通过 API 验证
```bash
# 检查节点是否存在
curl -s "http://10.0.0.213:8080/computer/unity-agent-i-0dff55811201880ed/" | grep "unity-agent"

# 检查 JNLP 端点
curl -I "http://10.0.0.213:8080/computer/unity-agent-i-0dff55811201880ed/jenkins-agent.jnlp"
```

## 常见问题

### 1. 节点名称不匹配
**问题**：Agent 脚本中的节点名称与 Jenkins 中创建的不一致。
**解决**：确保使用相同的 instance ID 格式。

### 2. Secret 过期
**问题**：Secret token 可能会过期或重新生成。
**解决**：重新访问节点页面获取最新的 secret。

### 3. 权限问题
**问题**：用户没有创建节点的权限。
**解决**：确保使用管理员账户登录。

## 自动化改进方向

未来可以考虑以下自动化方案：
1. 使用 Jenkins API Token 进行认证
2. 实现 CSRF token 自动获取
3. 创建专门的服务账户用于节点管理
4. 使用 Jenkins Configuration as Code (JCasC) 预配置节点模板