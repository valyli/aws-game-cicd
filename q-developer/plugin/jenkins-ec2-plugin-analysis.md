# Jenkins EC2 Plugin 实现方案分析

## 概述

基于 Jenkins EC2 Plugin 的动态 Agent 管理方案，保留 Jenkins Master 的自动化部署，但将 Agent 管理从固定 ASG 模式改为 Jenkins 原生的云动态管理模式。

## 当前架构 vs 目标架构

### 当前架构（问题）
```
Jenkins Master (CDK 部署)
├── 固定 ASG Agent 实例
├── 手动节点创建
├── 手动连接配置
└── 24/7 运行成本
```

### 目标架构（Plugin 方式）
```
Jenkins Master (CDK 部署)
├── EC2 Plugin 配置
├── 动态 Agent 模板
├── 按需创建/销毁
└── 成本优化
```

## Jenkins EC2 Plugin 工作原理

### 1. 核心组件
- **EC2 Cloud Configuration**: 定义 AWS 连接和基本设置
- **AMI Template**: 定义 Agent 实例的配置模板
- **Launch Template**: EC2 实例启动配置
- **Auto Scaling**: 基于队列长度自动扩缩容

### 2. 工作流程
```
构建任务排队 → Plugin 检测负载 → 启动 EC2 实例 → 自动连接 Agent → 执行任务 → 销毁实例
```

### 3. 关键特性
- **动态扩缩容**: 根据构建队列自动调整
- **Spot 实例支持**: 降低成本
- **多 AZ 部署**: 提高可用性
- **自动清理**: 任务完成后自动销毁

## 实现方案设计

### 阶段 1: 基础设施准备

#### 1.1 保留现有 Jenkins Master 部署
- 继续使用 CDK 部署 Jenkins Master
- 保留 VPC、安全组、ALB 等基础设施
- 确保 Jenkins Master 稳定运行

#### 1.2 移除固定 Agent ASG
- 删除 `jenkins_agent_stack.py` 中的 ASG 配置
- 保留 Agent 相关的 IAM 角色和安全组
- 清理不再需要的 Agent 启动脚本

#### 1.3 创建 Agent AMI
- 基于当前 Agent 配置创建标准 AMI
- 预装 Java、Git、Unity、Docker 等工具
- 包含自动连接到 Jenkins Master 的脚本

### 阶段 2: Jenkins EC2 Plugin 配置

#### 2.1 Plugin 安装和配置
```groovy
// Jenkins Configuration as Code (JCasC)
jenkins:
  clouds:
    - ec2:
        name: "unity-build-cloud"
        region: "us-east-1"
        useInstanceProfileForCredentials: true
        privateKey: ""  # 使用 IAM 角色
        instanceCapStr: "10"
        templates:
          - ami: "ami-xxxxxxxxx"  # Unity Agent AMI
            description: "Unity Build Agent"
            instanceType: "c5.large"
            securityGroups: "sg-xxxxxxxxx"
            subnetId: "subnet-xxxxxxxxx"
            type: SPOT
            spotConfig:
              spotMaxBidPrice: "0.10"
            labelString: "unity linux"
            mode: EXCLUSIVE
            numExecutors: 2
            remoteFS: "/opt/jenkins"
            initScript: |
              #!/bin/bash
              # Agent 初始化脚本
            userData: |
              #!/bin/bash
              # 用户数据脚本
```

#### 2.2 Agent 模板配置
- **实例类型**: c5.large, c5.xlarge (支持多种类型)
- **网络配置**: 私有子网 + NAT Gateway
- **存储配置**: GP3 SSD, 50GB 系统盘
- **标签配置**: unity, linux, build
- **生命周期**: 空闲 10 分钟后自动终止

### 阶段 3: CDK 集成

#### 3.1 新的 CDK 结构
```
jenkins-plugin-cdk/
├── app.py                    # CDK 应用入口
├── stacks/
│   ├── jenkins_master_stack.py    # Master 部署（保留）
│   ├── jenkins_plugin_stack.py    # Plugin 配置栈（新增）
│   ├── agent_ami_stack.py          # AMI 构建栈（新增）
│   └── vpc_stack.py               # VPC 配置（保留）
├── configs/
│   ├── jenkins.yaml              # JCasC 配置
│   └── ec2-plugin-config.yaml    # Plugin 配置
└── scripts/
    ├── build-agent-ami.sh        # AMI 构建脚本
    └── configure-plugin.sh       # Plugin 配置脚本
```

#### 3.2 Jenkins Master Stack 修改
- 保留现有的 Master 部署逻辑
- 添加 EC2 Plugin 的预配置
- 集成 JCasC 配置文件
- 确保必要的 IAM 权限

#### 3.3 新增 Plugin Configuration Stack
```python
class JenkinsPluginStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # EC2 Plugin 配置
        self._create_plugin_configuration()
        
        # Agent AMI 管理
        self._create_ami_management()
        
        # 监控和告警
        self._create_monitoring()
```

### 阶段 4: Agent AMI 构建

#### 4.1 AMI 构建流程
```bash
#!/bin/bash
# build-agent-ami.sh

# 1. 启动基础实例
# 2. 安装必要软件
# 3. 配置自动连接脚本
# 4. 创建 AMI
# 5. 更新 Plugin 配置
```

#### 4.2 Agent 自动连接脚本
```bash
#!/bin/bash
# agent-auto-connect.sh

# 获取 Jenkins Master 信息
JENKINS_URL=$(aws ssm get-parameter --name "/jenkins/master/url" --query 'Parameter.Value' --output text)

# 等待 Jenkins 可用
while ! curl -s $JENKINS_URL/login > /dev/null; do
    sleep 10
done

# 自动连接逻辑由 EC2 Plugin 处理
echo "Agent ready for connection"
```

## 技术实现细节

### 1. IAM 权限配置
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DescribeSnapshots",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeKeyPairs",
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:CreateTags",
        "ec2:RequestSpotInstances",
        "ec2:CancelSpotInstanceRequests"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2. 网络配置
- **Master**: 公有子网（通过 ALB 访问）
- **Agent**: 私有子网（通过 NAT Gateway 出网）
- **安全组**: Master 允许 Agent 连接 8080 端口

### 3. 成本优化
- **Spot 实例**: 节省 60-90% 成本
- **按需创建**: 只在有任务时创建
- **自动销毁**: 空闲后自动清理
- **多实例类型**: 提高 Spot 可用性

## 迁移计划

### 第 1 周: 准备阶段
- [ ] 创建 `jenkins-plugin-cdk` 项目结构
- [ ] 设计 Agent AMI 构建流程
- [ ] 准备 JCasC 配置文件
- [ ] 测试 EC2 Plugin 基本功能

### 第 2 周: AMI 构建
- [ ] 基于现有 Agent 配置构建 AMI
- [ ] 集成 Unity 和构建工具
- [ ] 测试 AMI 启动和连接
- [ ] 优化启动时间

### 第 3 周: Plugin 集成
- [ ] 在测试环境配置 EC2 Plugin
- [ ] 测试动态 Agent 创建和销毁
- [ ] 验证构建任务执行
- [ ] 性能和稳定性测试

### 第 4 周: 生产部署
- [ ] 部署新的 Plugin 配置
- [ ] 逐步迁移构建任务
- [ ] 监控成本和性能
- [ ] 移除旧的 ASG 配置

## 预期收益

### 成本优化
- **降低 60-90% Agent 成本**（使用 Spot 实例）
- **按需付费**（只为实际使用付费）
- **自动清理**（避免空闲资源浪费）

### 运维简化
- **零手动操作**（完全自动化）
- **弹性扩容**（自动应对负载变化）
- **标准化环境**（每次都是全新环境）

### 可靠性提升
- **故障隔离**（每个任务独立环境）
- **多 AZ 支持**（提高可用性）
- **自动恢复**（失败实例自动替换）

## 风险评估

### 技术风险
1. **启动时间**: EC2 实例启动需要 2-3 分钟
2. **网络配置**: 需要正确的 VPC 和安全组配置
3. **AMI 维护**: 需要定期更新 AMI
4. **Plugin 稳定性**: 依赖 Jenkins EC2 Plugin 的稳定性

### 缓解措施
1. **预热策略**: 保持少量预启动实例
2. **启动优化**: 优化 AMI 和启动脚本
3. **监控告警**: 实时监控成本和性能
4. **回滚计划**: 保留回滚到当前架构的能力

## 成功标准

### 功能标准
- [ ] Agent 能够自动创建和连接
- [ ] 构建任务正常执行
- [ ] 任务完成后 Agent 自动销毁
- [ ] 支持并发多个 Agent

### 性能标准
- [ ] Agent 启动时间 < 5 分钟
- [ ] 构建性能与现有方案相当
- [ ] 系统稳定性 > 99%

### 成本标准
- [ ] Agent 成本降低 > 60%
- [ ] 总体 TCO 降低 > 40%
- [ ] 资源利用率 > 80%

## 下一步行动

1. **立即开始**: 创建 `jenkins-plugin-cdk` 项目结构
2. **本周完成**: Agent AMI 构建流程设计
3. **下周开始**: EC2 Plugin 配置和测试
4. **月底目标**: 完成生产环境迁移

这个方案将彻底解决当前的手动操作问题，实现真正的云原生 Jenkins Agent 管理。