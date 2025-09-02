# Jenkins 云原生 Agent 架构设计

## 当前架构问题分析

### 现有架构的问题
我们当前使用的架构存在根本性设计问题：

❌ **固定 ASG 模式**：
- 使用 Auto Scaling Group 创建固定的 Agent 实例
- 需要手动在 Jenkins 中创建对应节点
- Agent 需要手动连接到预创建的节点
- 无法根据负载动态扩缩容
- 成本效率低（实例持续运行）

❌ **手动节点管理**：
- 每个 Agent 实例需要手动创建 Jenkins 节点
- 节点名称需要手动匹配
- Secret 管理复杂
- 无法自动清理离线节点

## 正确的云原生架构

### Jenkins 在 AWS 上的标准做法

✅ **动态 Agent 管理**：
```
Jenkins Master → EC2 Plugin → 动态创建 EC2 实例 → 自动配置 Agent → 任务完成后销毁
```

### 工作流程

1. **任务排队**：构建任务进入 Jenkins 队列
2. **资源评估**：Jenkins 检查可用 Agent 资源
3. **动态创建**：通过 EC2 Plugin 自动启动新 EC2 实例
4. **自动配置**：实例启动后自动安装 Agent 并连接到 Master
5. **执行任务**：Agent 执行构建任务
6. **自动销毁**：任务完成后自动销毁实例（节省成本）

### 核心组件

#### 1. Jenkins EC2 Plugin
- **功能**：管理 EC2 实例生命周期
- **配置**：AMI 模板、实例类型、安全组、子网
- **扩缩容**：根据队列长度自动扩缩容

#### 2. Agent AMI 模板
- **预装软件**：Java、Git、Unity、Docker 等
- **自动配置**：启动时自动连接到 Jenkins Master
- **标准化**：统一的构建环境

#### 3. 动态扩缩容策略
- **按需创建**：有任务时创建，无任务时销毁
- **Spot 实例**：使用 Spot 实例降低成本
- **多实例类型**：支持多种实例类型提高可用性

## 架构对比

### 当前架构（有问题）
```
Jenkins Master
├── 固定 ASG
│   ├── Agent 实例 1 (持续运行)
│   ├── Agent 实例 2 (持续运行)
│   └── Agent 实例 N (持续运行)
├── 手动节点创建
├── 手动 Secret 管理
└── 固定成本（24/7 运行）
```

### 正确架构（云原生）
```
Jenkins Master
├── EC2 Plugin 配置
│   ├── AMI 模板配置
│   ├── 实例类型配置
│   ├── 网络配置
│   └── 扩缩容策略
├── 动态 Agent 池
│   ├── 按需创建实例
│   ├── 自动节点注册
│   ├── 任务执行
│   └── 自动销毁
└── 成本优化（按使用付费）
```

## 实现方案

### 1. Jenkins EC2 Plugin 配置

#### 基本配置
```groovy
// Jenkins Configuration as Code (JCasC)
jenkins:
  clouds:
    - ec2:
        name: "unity-build-cloud"
        region: "us-east-1"
        useInstanceProfileForCredentials: true
        templates:
          - ami: "ami-xxxxxxxxx"  # Unity Build AMI
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
            userData: |
              #!/bin/bash
              # Auto-configure agent connection
```

#### 高级配置
- **多 AZ 部署**：跨多个可用区部署提高可用性
- **混合实例**：On-Demand + Spot 实例组合
- **自动扩缩容**：基于队列长度和等待时间
- **实例生命周期**：空闲超时自动终止

### 2. Agent AMI 构建

#### AMI 内容
```bash
# 预装软件
- Amazon Linux 2023
- Java 17 (Amazon Corretto)
- Git
- Docker
- Unity Hub & Unity Editor
- AWS CLI
- Jenkins Agent 自动连接脚本
```

#### 自动连接脚本
```bash
#!/bin/bash
# 实例启动时自动执行
# 1. 获取 Jenkins Master 信息
# 2. 下载 agent.jar
# 3. 自动连接到 Master
# 4. 注册为可用 Agent
```

### 3. 网络和安全配置

#### 安全组规则
```
Agent Security Group:
- 出站：允许访问 Jenkins Master (8080)
- 出站：允许 HTTPS (443) 用于下载依赖
- 出站：允许 HTTP (80) 用于包管理

Master Security Group:
- 入站：允许 Agent 访问 (8080)
- 入站：允许 ALB 访问 (8080)
```

#### 网络配置
- **私有子网**：Agent 部署在私有子网
- **NAT Gateway**：提供出站网络访问
- **VPC Endpoints**：访问 AWS 服务（可选）

## 迁移计划

### 阶段 1：准备工作
1. **创建 Unity Build AMI**
   - 基于当前 Agent 配置创建 AMI
   - 添加自动连接脚本
   - 测试 AMI 功能

2. **配置 EC2 Plugin**
   - 在 Jenkins 中安装 EC2 Plugin
   - 配置 AWS 凭证和权限
   - 设置基本的 Agent 模板

### 阶段 2：并行测试
1. **保持现有架构**
   - 继续使用当前的 ASG 模式
   - 确保业务连续性

2. **测试新架构**
   - 创建测试用的 EC2 Cloud 配置
   - 运行少量测试任务
   - 验证动态创建和销毁功能

### 阶段 3：逐步迁移
1. **切换部分任务**
   - 将非关键任务迁移到新架构
   - 监控性能和稳定性
   - 收集成本数据

2. **完全迁移**
   - 所有任务迁移到新架构
   - 移除旧的 ASG 配置
   - 清理相关资源

### 阶段 4：优化
1. **成本优化**
   - 调整 Spot 实例配置
   - 优化实例类型选择
   - 设置合理的超时时间

2. **性能优化**
   - 优化 AMI 启动时间
   - 调整扩缩容策略
   - 监控和告警配置

## 预期收益

### 成本优化
- **按需付费**：只为实际使用的计算资源付费
- **Spot 实例**：相比 On-Demand 节省 60-90% 成本
- **自动销毁**：避免空闲资源浪费

### 运维简化
- **自动管理**：无需手动创建和管理节点
- **弹性扩容**：自动应对负载变化
- **标准化环境**：每次都是全新的标准环境

### 可靠性提升
- **故障隔离**：每个任务使用独立实例
- **多 AZ 部署**：提高可用性
- **自动恢复**：失败实例自动替换

## 技术风险和缓解

### 风险评估
1. **启动时间**：EC2 实例启动需要时间
2. **网络配置**：需要正确的 VPC 和安全组配置
3. **AMI 维护**：需要定期更新 AMI
4. **成本控制**：需要合理的超时和限制策略

### 缓解措施
1. **预热策略**：保持少量预启动实例
2. **启动优化**：优化 AMI 和启动脚本
3. **监控告警**：实时监控成本和性能
4. **回滚计划**：保留回滚到旧架构的能力

## 实施时间线

### 第 1-2 周：准备阶段
- 创建和测试 Unity Build AMI
- 配置 Jenkins EC2 Plugin
- 设置测试环境

### 第 3-4 周：测试阶段
- 并行运行新旧架构
- 执行功能和性能测试
- 收集数据和反馈

### 第 5-6 周：迁移阶段
- 逐步迁移生产任务
- 监控稳定性和性能
- 优化配置参数

### 第 7-8 周：优化阶段
- 成本和性能优化
- 完善监控和告警
- 文档和培训

## 结论

当前的固定 ASG + 手动节点创建模式不是 Jenkins 在云环境中的最佳实践。正确的做法是使用 Jenkins EC2 Plugin 实现真正的云原生动态 Agent 管理。

这种架构不仅能显著降低成本，还能提供更好的可扩展性、可靠性和运维效率。建议在当前修复验证完成后，启动向云原生架构的迁移工作。