# Jenkins Unity CI/CD CDK实施任务清单

## 项目概述
基于设计文档实现完整的Jenkins Unity CI/CD系统，使用AWS CDK (Python)进行基础设施即代码部署。

## 阶段1: 项目初始化和基础设施 (第1-2天)

### 任务1.1: CDK项目初始化
- [ ] 创建CDK Python项目结构
- [ ] 配置项目依赖 (requirements.txt)
- [ ] 设置CDK配置文件 (cdk.json)
- [ ] 创建自定义前缀配置系统
- [ ] 设置环境变量和参数管理

**交付物:**
```
jenkins-unity-cdk/
├── app.py                 # CDK应用入口
├── requirements.txt       # Python依赖
├── cdk.json              # CDK配置
├── config/               # 配置文件目录
│   ├── default.yaml
│   └── production.yaml
└── stacks/               # CDK栈目录
```

### 任务1.2: VPC和网络基础设施
- [ ] 创建VPC栈 (JenkinsVpcStack)
- [ ] 配置3个AZ的公有/私有子网
- [ ] 创建Internet Gateway和NAT Gateway
- [ ] 配置路由表
- [ ] 创建VPC端点 (S3, DynamoDB, EFS)

**关键组件:**
- VPC: 10.0.0.0/16
- 公有子网: 10.0.1.0/24, 10.0.2.0/24, 10.0.3.0/24
- 私有子网: 10.0.11.0/24, 10.0.12.0/24, 10.0.13.0/24

### 任务1.3: 安全组配置
- [ ] Jenkins Master安全组
- [ ] Jenkins Agent安全组  
- [ ] ALB安全组
- [ ] EFS安全组
- [ ] Lambda安全组

## 阶段2: 存储和数据服务 (第3天)

### 任务2.1: EFS文件系统
- [ ] 创建EFS文件系统
- [ ] 配置加密 (传输和静态)
- [ ] 设置性能模式 (General Purpose)
- [ ] 配置吞吐量模式 (Provisioned 100 MiB/s)
- [ ] 创建挂载目标 (每个AZ)

### 任务2.2: DynamoDB缓存池状态表
- [ ] 创建DynamoDB表 (jenkins-cache-pool-status)
- [ ] 配置主键 (VolumeId)
- [ ] 创建GSI索引 (AZ-Status-Index, Project-Status-Index)
- [ ] 设置属性定义
- [ ] 配置加密

### 任务2.3: S3存储桶
- [ ] 构建产物存储桶 (带唯一后缀)
- [ ] 缓存模板存储桶
- [ ] 日志存储桶
- [ ] 配置生命周期策略
- [ ] 设置加密和访问策略

## 阶段3: IAM角色和权限 (第4天)

### 任务3.1: Jenkins Master IAM角色
- [ ] EC2基础权限
- [ ] EFS访问权限
- [ ] S3读写权限
- [ ] Lambda调用权限
- [ ] CloudWatch日志权限
- [ ] EC2管理权限 (Spot实例)

### 任务3.2: Jenkins Agent IAM角色
- [ ] EBS卷attach/detach权限
- [ ] S3读写权限
- [ ] Lambda调用权限
- [ ] CloudWatch日志权限
- [ ] Systems Manager权限 (Unity许可证)

### 任务3.3: Lambda执行角色
- [ ] DynamoDB读写权限
- [ ] EC2卷管理权限
- [ ] CloudWatch日志权限

## 阶段4: Lambda函数开发 (第5-6天)

### 任务4.1: 缓存卷分配Lambda
- [ ] 实现allocate_cache_volume函数
- [ ] DynamoDB查询逻辑
- [ ] EBS卷创建逻辑
- [ ] 错误处理和重试机制
- [ ] 单元测试

**核心功能:**
```python
def lambda_handler(event, context):
    # 1. 解析请求参数 (AZ, project_id)
    # 2. 查询可用缓存卷
    # 3. 分配现有卷或创建新卷
    # 4. 更新DynamoDB状态
    # 5. 返回卷ID
```

### 任务4.2: 缓存卷回收Lambda
- [ ] 实现release_cache_volume函数
- [ ] EBS卷分离逻辑
- [ ] DynamoDB状态更新
- [ ] 错误处理
- [ ] 单元测试

### 任务4.3: 缓存池维护Lambda
- [ ] 实现maintain_cache_pool函数
- [ ] 清理长期未使用的卷
- [ ] 确保最小卷数量
- [ ] 创建快照备份
- [ ] CloudWatch事件触发 (定时执行)

## 阶段5: Jenkins Master部署 (第7-8天)

### 任务5.1: Jenkins Master EC2配置
- [ ] 创建Launch Template
- [ ] 配置用户数据脚本 (EFS挂载, Jenkins启动)
- [ ] Auto Scaling Group配置 (min=1, max=1)
- [ ] 公有子网部署
- [ ] 安全组关联

### 任务5.2: Application Load Balancer
- [ ] 创建ALB
- [ ] 配置监听器 (HTTP->HTTPS重定向)
- [ ] SSL证书配置 (可选)
- [ ] 目标组配置
- [ ] 健康检查设置

### 任务5.3: Jenkins配置管理
- [ ] JCasC配置文件
- [ ] 插件列表管理
- [ ] 初始化脚本
- [ ] 备份策略

## 阶段6: AMI构建自动化 (第9-10天)

### 任务6.1: Packer模板
- [ ] Jenkins Master Packer模板 (jenkins-master.pkr.hcl)
- [ ] Unity Agent Packer模板 (unity-agent.pkr.hcl)
- [ ] 变量参数化 (project_prefix, unity_version)
- [ ] 构建脚本集成

### 任务6.2: AMI构建脚本
- [ ] 一键构建脚本 (build-amis.sh)
- [ ] Jenkins Master安装脚本
- [ ] Unity Agent安装脚本 (Unity Editor, Android SDK)
- [ ] 环境配置和优化

### 任务6.3: CodeBuild集成 (可选)
- [ ] buildspec.yml配置
- [ ] CodeBuild项目创建
- [ ] 自动触发机制
- [ ] 构建产物管理

## 阶段7: Spot实例Agent配置 (第11-12天)

### 任务7.1: Agent Launch Template
- [ ] 创建Launch Template
- [ ] 多实例类型配置
- [ ] 用户数据脚本 (缓存卷分配和挂载)
- [ ] 安全组配置
- [ ] IAM实例配置文件

### 任务7.2: Auto Scaling Group
- [ ] Mixed Instances Policy配置
- [ ] Spot分配策略 (diversified)
- [ ] 跨AZ部署
- [ ] 扩缩容策略
- [ ] 实例刷新配置

### 任务7.3: Spot中断处理
- [ ] 中断监听脚本
- [ ] 优雅关闭逻辑
- [ ] 缓存卷回收
- [ ] Jenkins通知机制

## 阶段8: 监控和日志 (第13天)

### 任务8.1: CloudWatch监控
- [ ] 自定义指标定义
- [ ] Dashboard创建
- [ ] 告警规则配置
- [ ] SNS通知设置

**关键指标:**
- 可用缓存卷数量
- Spot实例中断率
- 构建队列长度
- 系统资源使用率

### 任务8.2: 日志管理
- [ ] CloudWatch日志组创建
- [ ] 日志保留策略
- [ ] 日志聚合配置
- [ ] 日志分析查询

## 阶段9: 部署脚本和文档 (第14天)

### 任务9.1: 部署自动化
- [ ] 一键部署脚本 (deploy.sh)
- [ ] 参数验证
- [ ] 依赖检查
- [ ] 部署后验证

### 任务9.2: 配置管理
- [ ] 环境特定配置
- [ ] 参数存储集成
- [ ] 密钥管理 (Unity许可证)
- [ ] 配置验证

### 任务9.3: 文档完善
- [ ] 部署指南
- [ ] 运维手册
- [ ] 故障排除指南
- [ ] API文档

## 阶段10: 测试和验证 (第15天)

### 任务10.1: 集成测试
- [ ] 端到端部署测试
- [ ] Jenkins Master启动验证
- [ ] Agent连接测试
- [ ] 缓存池功能测试
- [ ] Spot中断恢复测试

### 任务10.2: 性能测试
- [ ] 构建性能基准测试
- [ ] 缓存效果验证
- [ ] 并发构建测试
- [ ] 资源使用分析

### 任务10.3: 安全测试
- [ ] 安全组规则验证
- [ ] IAM权限最小化检查
- [ ] 加密配置验证
- [ ] 访问控制测试

## 项目结构规划

```
jenkins-unity-cdk/
├── app.py                          # CDK应用入口
├── requirements.txt                # Python依赖
├── cdk.json                       # CDK配置
├── README.md                      # 项目说明
├── deploy.sh                      # 一键部署脚本
├── config/                        # 配置文件
│   ├── default.yaml
│   ├── development.yaml
│   └── production.yaml
├── stacks/                        # CDK栈
│   ├── __init__.py
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
│   ├── jenkins-master-setup.sh
│   └── unity-agent-setup.sh
├── packer/                        # Packer模板
│   ├── jenkins-master.pkr.hcl
│   └── unity-agent.pkr.hcl
├── configs/                       # Jenkins配置
│   ├── jenkins.yaml              # JCasC配置
│   └── plugins.txt               # 插件列表
└── tests/                         # 测试代码
    ├── unit/
    └── integration/
```

## 关键里程碑

- **第3天**: 基础设施就绪 (VPC, 存储, 权限)
- **第6天**: Lambda函数完成
- **第8天**: Jenkins Master可访问
- **第10天**: AMI构建自动化完成
- **第12天**: Spot Agent正常工作
- **第15天**: 完整系统测试通过

## 风险和依赖

### 高风险任务
1. **Unity许可证配置** - 需要有效的Unity许可证
2. **EBS缓存池逻辑** - 复杂的状态管理
3. **Spot中断处理** - 需要充分测试

### 外部依赖
1. AWS账户和权限
2. Unity许可证
3. GitHub/Git仓库访问
4. 域名和SSL证书 (可选)

### 建议的实施顺序
1. 先实现基础设施 (VPC, 存储)
2. 再实现核心逻辑 (Lambda, Jenkins)
3. 最后实现自动化 (AMI构建, 部署脚本)
4. 持续测试和优化

这个任务清单提供了详细的实施路径，每个任务都有明确的交付物和验收标准。建议按阶段逐步实施，确保每个阶段完成后再进入下一阶段。