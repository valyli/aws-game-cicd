# EBS缓存池设计文档

## 概述
为Windows Jenkins Agent实现EBS缓存池机制，实现构建缓存的持久化和复用，提升构建效率并降低成本。

## 设计目标
1. **持久化缓存**：构建缓存不随实例消失，可在实例间复用
2. **自动管理**：EBS卷的分配、挂载、释放全自动化
3. **成本优化**：通过缓存复用减少重复下载和构建时间
4. **高可用性**：支持跨AZ的卷分配和故障恢复

## 架构设计

### 1. EBS缓存池管理
- **DynamoDB表**：`unity-cicd-cache-pool-status`
  - 主键：`VolumeId`
  - 属性：`Status`, `AvailabilityZone`, `ProjectId`, `InstanceId`, `CreatedTime`, `LastUsed`
  - GSI：`AZ-Status-Index` (AvailabilityZone, Status)

### 2. Lambda函数
- **allocate-cache-volume**：分配可用EBS卷
- **release-cache-volume**：释放EBS卷回池
- **maintain-cache-pool**：定期清理和维护缓存池

### 3. EBS卷状态管理
```
Available -> InUse -> Available
     ↓         ↓         ↑
  Creating  Attached  Released
```

## 详细设计

### 1. EBS卷分配逻辑

#### Lambda函数如何知道可分配的EBS卷？
1. **DynamoDB查询**：
   ```python
   # 查询指定AZ中状态为Available的卷
   response = table.query(
       IndexName='AZ-Status-Index',
       KeyConditionExpression='AvailabilityZone = :az AND Status = :status',
       ExpressionAttributeValues={
           ':az': availability_zone,
           ':status': 'Available'
       }
   )
   ```

2. **卷状态定义**：
   - `Available`：可分配给新实例
   - `InUse`：正在被实例使用
   - `Creating`：正在创建中
   - `Maintenance`：维护中，不可分配

3. **分配策略**：
   - 优先分配最近使用的卷（热缓存）
   - 同项目优先（ProjectId匹配）
   - 如无可用卷则创建新卷

### 2. 缓存目录结构
```
D:\jenkins-cache\
├── workspace\          # Jenkins工作空间
├── git-cache\          # Git仓库缓存
├── unity-cache\        # Unity构建缓存
├── nuget-cache\        # NuGet包缓存
├── temp\              # 临时文件（定期清理）
└── cleanup-cache.bat   # 清理脚本
```

### 3. 自动清理机制

#### 临时文件清理位置和逻辑：
1. **清理脚本位置**：`D:\jenkins-cache\cleanup-cache.bat`
2. **清理目标**：`D:\jenkins-cache\temp\` 目录
3. **清理策略**：删除7天前的文件
4. **执行时机**：
   - Jenkins构建完成后触发
   - 定期通过Windows任务计划程序执行
   - 实例启动时执行一次

### 4. 卷释放机制优化

#### 使用EC2生命周期管理：
1. **EC2 Instance Lifecycle Hooks**：
   ```python
   # 在Auto Scaling Group中配置生命周期钩子
   lifecycle_hook = {
       'LifecycleHookName': 'jenkins-agent-terminating',
       'AutoScalingGroupName': 'jenkins-windows-agents',
       'LifecycleTransition': 'autoscaling:EC2_INSTANCE_TERMINATING',
       'HeartbeatTimeout': 300,
       'NotificationTargetARN': 'arn:aws:sqs:region:account:jenkins-lifecycle-queue'
   }
   ```

2. **SQS + Lambda处理**：
   - SQS接收生命周期事件
   - Lambda函数处理卷释放
   - 确保卷在实例终止前正确分离

3. **CloudWatch Events**：
   - 监听EC2实例状态变化
   - 触发卷释放流程

## 实现任务清单

### Phase 1: 基础设施准备
- [ ] 验证DynamoDB表结构和索引
- [ ] 确认Lambda函数部署状态
- [ ] 测试Lambda函数的卷分配逻辑
- [ ] 验证IAM权限配置

### Phase 2: Windows Agent脚本改进
- [ ] 修复diskpart脚本（检测正确的磁盘编号）
- [ ] 改进卷挂载等待逻辑
- [ ] 添加卷挂载失败的回退机制
- [ ] 优化环境变量设置

### Phase 3: 生命周期管理
- [ ] 实现EC2生命周期钩子
- [ ] 创建SQS队列和Lambda处理器
- [ ] 测试实例终止时的卷释放
- [ ] 添加异常处理和重试机制

### Phase 4: 缓存优化
- [ ] 实现智能缓存清理策略
- [ ] 添加缓存使用统计
- [ ] 优化Git和Unity缓存配置
- [ ] 实现缓存预热机制

### Phase 5: 监控和维护
- [ ] 添加CloudWatch指标
- [ ] 实现缓存池健康检查
- [ ] 创建运维仪表板
- [ ] 编写故障排查文档

## 风险和缓解措施

### 1. 卷挂载失败
- **风险**：新创建的卷可能需要初始化时间
- **缓解**：增加等待时间，添加重试机制

### 2. 磁盘编号识别错误
- **风险**：diskpart可能选择错误的磁盘
- **缓解**：通过设备路径和卷大小确认正确磁盘

### 3. 生命周期钩子超时
- **风险**：卷释放操作可能超时
- **缓解**：异步处理，增加心跳延长机制

### 4. 缓存数据一致性
- **风险**：多实例同时使用同一卷
- **缓解**：严格的状态管理和锁机制

## 性能预期

### 构建时间优化：
- **首次构建**：与现有方案相同
- **后续构建**：预期减少30-50%构建时间
- **Git克隆**：从缓存复用，减少90%时间
- **Unity资源导入**：缓存复用，减少60-80%时间

### 成本影响：
- **EBS存储成本**：增加（但通过构建时间减少抵消）
- **EC2计算成本**：减少（构建时间缩短）
- **整体成本**：预期减少20-30%

## 下一步行动
1. 先修复当前Windows Agent脚本的技术问题
2. 逐步实现生命周期管理
3. 进行小规模测试验证
4. 收集性能数据并优化