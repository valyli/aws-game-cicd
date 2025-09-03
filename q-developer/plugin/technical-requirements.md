# Jenkins EC2 Plugin 技术需求规格

## 系统架构需求

### 1. 整体架构
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Developer     │    │   Jenkins        │    │   Dynamic       │
│   Push Code     │───▶│   Master         │───▶│   EC2 Agents    │
│                 │    │   (CDK Deployed) │    │   (Plugin Mgmt) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │                         │
                              ▼                         ▼
                       ┌──────────────┐         ┌──────────────┐
                       │   ALB +      │         │   Spot       │
                       │   EFS +      │         │   Instances  │
                       │   RDS        │         │   Auto Scale │
                       └──────────────┘         └──────────────┘
```

### 2. 核心组件需求

#### 2.1 Jenkins Master (保留现有 + 增强)
- **部署方式**: CDK 自动化部署
- **实例类型**: t3.medium 或 t3.large
- **网络**: 公有子网 + ALB
- **存储**: EFS 共享存储
- **插件**: EC2 Plugin + JCasC Plugin
- **配置**: Configuration as Code

#### 2.2 EC2 Plugin 配置
- **云提供商**: AWS EC2
- **认证方式**: IAM 角色 (无需密钥)
- **实例管理**: 动态创建/销毁
- **扩缩容**: 基于队列长度
- **成本优化**: Spot 实例优先

#### 2.3 Agent 实例规格
```yaml
实例类型:
  - c5.large:   2 vCPU, 4GB RAM  (轻量构建)
  - c5.xlarge:  4 vCPU, 8GB RAM  (标准构建)
  - c5.2xlarge: 8 vCPU, 16GB RAM (重型构建)

网络配置:
  - 子网: 私有子网
  - 安全组: 允许访问 Master 8080 端口
  - 出网: NAT Gateway

存储配置:
  - 系统盘: 50GB GP3 SSD
  - 临时存储: 实例存储 (如可用)
  - 缓存: EFS 挂载 (可选)
```

## 功能需求

### 1. 自动化 Agent 管理

#### 1.1 动态创建
```yaml
触发条件:
  - 构建队列长度 > 0
  - 等待时间 > 1 分钟
  - 可用 Agent 数量 < 需求

创建流程:
  1. 检查实例配额和限制
  2. 选择最优实例类型和 AZ
  3. 启动 Spot 实例 (优先) 或 On-Demand
  4. 等待实例就绪
  5. 自动连接到 Jenkins Master
  6. 开始执行构建任务
```

#### 1.2 自动销毁
```yaml
销毁条件:
  - 空闲时间 > 10 分钟
  - 构建任务完成
  - Spot 实例中断通知

销毁流程:
  1. 完成当前任务
  2. 清理工作目录
  3. 断开 Jenkins 连接
  4. 终止 EC2 实例
  5. 清理相关资源
```

### 2. 构建环境标准化

#### 2.1 预装软件清单
```bash
基础环境:
  - Amazon Linux 2023
  - Java 17 (Amazon Corretto)
  - Git 2.x
  - Docker 24.x
  - AWS CLI v2

Unity 开发环境:
  - Unity Hub
  - Unity Editor (多版本支持)
  - Unity Build Tools
  - Android SDK (如需要)
  - iOS Build Tools (如需要)

构建工具:
  - Maven 3.x
  - Gradle 8.x
  - Node.js 18.x
  - Python 3.11
```

#### 2.2 环境配置
```yaml
用户配置:
  - jenkins 用户 (uid: 1000)
  - docker 组成员
  - sudo 权限 (受限)

目录结构:
  - /opt/jenkins: Jenkins 工作目录
  - /opt/unity: Unity 安装目录
  - /tmp/build: 临时构建目录
  - /var/cache: 构建缓存目录

环境变量:
  - JAVA_HOME: /usr/lib/jvm/java-17-amazon-corretto
  - UNITY_HOME: /opt/unity
  - DOCKER_HOST: unix:///var/run/docker.sock
```

### 3. 网络和安全需求

#### 3.1 网络配置
```yaml
VPC 配置:
  - CIDR: 10.0.0.0/16
  - 公有子网: 10.0.1.0/24, 10.0.2.0/24, 10.0.3.0/24
  - 私有子网: 10.0.11.0/24, 10.0.12.0/24, 10.0.13.0/24

安全组规则:
  Master SG:
    - 入站: ALB (80, 443), Agent (8080)
    - 出站: 全部允许
  
  Agent SG:
    - 入站: SSH (22) 仅限管理
    - 出站: HTTPS (443), Master (8080)
  
  ALB SG:
    - 入站: HTTP (80), HTTPS (443) 全网
    - 出站: Master (8080)
```

#### 3.2 IAM 权限
```json
Jenkins Master 角色权限:
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
        "ec2:CancelSpotInstanceRequests",
        "ec2:DescribeSpotInstanceRequests",
        "ec2:DescribeSpotPriceHistory"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:PassRole"
      ],
      "Resource": "arn:aws:iam::*:role/jenkins-agent-role"
    }
  ]
}

Agent 角色权限:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::unity-build-artifacts/*",
        "arn:aws:s3:::unity-build-cache/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters"
      ],
      "Resource": "arn:aws:ssm:*:*:parameter/jenkins/*"
    }
  ]
}
```

## 性能需求

### 1. 响应时间要求
```yaml
Agent 启动时间:
  - 目标: < 3 分钟
  - 最大: < 5 分钟
  - 测量: 从请求到可用

构建性能:
  - Unity 项目构建: 与现有性能相当
  - 并发构建: 支持 10+ 并发任务
  - 资源利用率: > 80%

系统可用性:
  - 目标: 99.5%
  - Jenkins Master: 99.9%
  - Agent 可用性: 99%
```

### 2. 扩缩容要求
```yaml
扩容策略:
  - 触发条件: 队列等待 > 1 分钟
  - 扩容速度: 每分钟最多 3 个实例
  - 最大实例数: 20 个

缩容策略:
  - 触发条件: 空闲 > 10 分钟
  - 缩容速度: 每分钟最多 2 个实例
  - 最小实例数: 0 个

负载均衡:
  - 任务分配: 基于 Agent 负载
  - 实例类型选择: 基于任务需求
  - AZ 分布: 均匀分布
```

## 成本需求

### 1. 成本目标
```yaml
成本降低目标:
  - Agent 成本: 降低 60-90%
  - 总体 TCO: 降低 40-60%
  - 资源浪费: 减少 80%

成本控制措施:
  - Spot 实例优先: 90% 使用 Spot
  - 自动销毁: 空闲 10 分钟后销毁
  - 实例类型优化: 基于任务需求选择
  - 预算告警: 月度成本超过阈值告警
```

### 2. Spot 实例策略
```yaml
Spot 配置:
  - 最大出价: On-Demand 价格的 50%
  - 实例类型: 多样化 (c5.large, c5.xlarge, m5.large)
  - 可用区: 多 AZ 分布
  - 中断处理: 优雅关闭 + 任务重试

回退策略:
  - Spot 不可用时使用 On-Demand
  - 关键任务优先使用 On-Demand
  - 成本监控和告警
```

## 监控和运维需求

### 1. 监控指标
```yaml
系统指标:
  - Agent 创建/销毁次数
  - Agent 启动时间分布
  - 构建任务成功率
  - 资源利用率

成本指标:
  - 每小时 Agent 成本
  - Spot vs On-Demand 比例
  - 资源浪费率
  - 月度成本趋势

性能指标:
  - 构建队列长度
  - 平均等待时间
  - 构建执行时间
  - 并发任务数量
```

### 2. 告警配置
```yaml
关键告警:
  - Agent 启动失败率 > 10%
  - 构建队列等待 > 10 分钟
  - 月度成本超过预算 20%
  - Jenkins Master 不可用

警告告警:
  - Agent 启动时间 > 5 分钟
  - Spot 实例中断率 > 50%
  - 资源利用率 < 60%
  - 构建失败率 > 5%
```

### 3. 日志管理
```yaml
日志收集:
  - Jenkins Master 日志
  - Agent 启动和运行日志
  - EC2 Plugin 操作日志
  - 构建任务日志

日志存储:
  - CloudWatch Logs
  - 保留期: 30 天
  - 搜索和分析: CloudWatch Insights
  - 告警: 基于日志模式
```

## 安全需求

### 1. 访问控制
```yaml
Jenkins 访问:
  - 基于角色的访问控制 (RBAC)
  - LDAP/AD 集成 (可选)
  - API Token 管理
  - 审计日志

Agent 访问:
  - 仅通过 Jenkins Master 访问
  - 无直接 SSH 访问
  - IAM 角色认证
  - 网络隔离
```

### 2. 数据安全
```yaml
传输加密:
  - Jenkins Master ↔ Agent: TLS
  - ALB ↔ Jenkins: HTTPS
  - 构建产物: S3 加密

存储加密:
  - EFS: 静态加密
  - EBS: 静态加密
  - S3: 服务端加密
  - 参数存储: KMS 加密

密钥管理:
  - AWS KMS 管理密钥
  - 参数存储敏感信息
  - 定期密钥轮换
  - 最小权限原则
```

## 兼容性需求

### 1. 现有系统兼容
```yaml
Jenkins 版本:
  - 最低版本: 2.400+
  - LTS 版本优先
  - 插件兼容性验证

构建脚本:
  - 现有 Jenkinsfile 无需修改
  - 环境变量保持一致
  - 构建工具版本兼容

Unity 项目:
  - Unity 2021.3 LTS+
  - 多版本并存支持
  - 项目设置兼容
```

### 2. 迁移兼容
```yaml
数据迁移:
  - Jenkins 配置迁移
  - 构建历史保留
  - 用户权限迁移
  - 插件配置迁移

回滚支持:
  - 配置备份
  - 快速回滚机制
  - 数据一致性保证
  - 最小停机时间
```

## 测试需求

### 1. 功能测试
```yaml
基本功能:
  - Agent 自动创建和连接
  - 构建任务正常执行
  - Agent 自动销毁
  - 多并发任务支持

异常处理:
  - Spot 实例中断处理
  - 网络故障恢复
  - Agent 启动失败处理
  - 构建任务失败重试
```

### 2. 性能测试
```yaml
负载测试:
  - 10+ 并发构建任务
  - 持续 24 小时运行
  - 峰值负载处理
  - 资源利用率测试

压力测试:
  - 最大实例数测试
  - 快速扩缩容测试
  - 系统极限测试
  - 故障恢复测试
```

### 3. 安全测试
```yaml
访问控制测试:
  - 未授权访问阻止
  - 权限边界验证
  - API 安全测试
  - 网络隔离验证

数据安全测试:
  - 传输加密验证
  - 存储加密验证
  - 密钥管理测试
  - 审计日志完整性
```

这些技术需求将确保 Jenkins EC2 Plugin 方案的成功实施，实现高性能、低成本、高可靠性的云原生 CI/CD 系统。