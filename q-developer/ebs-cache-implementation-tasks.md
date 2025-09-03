# EBS缓存池实现任务清单

## 当前问题分析

### 1. Windows Agent脚本问题
- **磁盘识别问题**：`select disk 1` 可能不正确，需要动态识别
- **卷挂载等待**：30秒可能不够，需要检查挂载状态
- **错误处理**：缺少挂载失败的回退机制
- **清理脚本位置**：应该在实例启动时就创建并调度

### 2. 生命周期管理问题
- **注册表方式不可靠**：Windows关机脚本可能不执行
- **需要EC2生命周期钩子**：更可靠的实例终止处理

### 3. Lambda函数状态管理
- **DynamoDB查询逻辑**：已存在但需要验证
- **卷状态同步**：需要确保状态一致性

## 立即修复任务

### Task 1: 修复Windows Agent脚本
**优先级：高**

#### 1.1 改进磁盘识别逻辑
```batch
REM 当前问题：硬编码 disk 1
echo select disk 1 > diskpart_script.txt

REM 改进方案：动态识别新挂载的磁盘
powershell -Command "Get-Disk | Where-Object {$_.PartitionStyle -eq 'RAW' -and $_.Size -gt 50GB} | Select-Object -First 1 -ExpandProperty Number" > disk_number.txt
set /p DISK_NUMBER=<disk_number.txt
echo select disk %DISK_NUMBER% > diskpart_script.txt
```

#### 1.2 改进卷挂载等待逻辑
```batch
REM 当前问题：固定等待30秒
timeout /t 30 /nobreak >nul

REM 改进方案：循环检查直到卷可用
:WAIT_VOLUME
powershell -Command "Get-Disk | Where-Object {$_.PartitionStyle -eq 'RAW'}" > nul 2>&1
if %errorlevel% neq 0 (
    echo Waiting for volume attachment... >> %LOG_FILE%
    timeout /t 10 /nobreak >nul
    goto WAIT_VOLUME
)
```

#### 1.3 添加挂载失败回退机制
```batch
REM 检查D盘是否成功挂载
if exist D:\ (
    set CACHE_DIR=D:\jenkins-cache
    echo Cache volume mounted successfully >> %LOG_FILE%
) else (
    echo WARNING: Cache volume mount failed, using local storage >> %LOG_FILE%
    set CACHE_DIR=C:\jenkins-cache
)
```

### Task 2: 实现EC2生命周期管理
**优先级：高**

#### 2.1 创建生命周期钩子配置
```python
# 在CDK中添加Auto Scaling生命周期钩子
lifecycle_hook = autoscaling.LifecycleHook(
    self, "JenkinsAgentTerminatingHook",
    auto_scaling_group=asg,
    lifecycle_transition=autoscaling.LifecycleTransition.INSTANCE_TERMINATING,
    heartbeat_timeout=Duration.minutes(5),
    notification_target=sqs_queue
)
```

#### 2.2 创建SQS队列和Lambda处理器
```python
# SQS队列接收生命周期事件
lifecycle_queue = sqs.Queue(
    self, "JenkinsLifecycleQueue",
    visibility_timeout=Duration.minutes(6)
)

# Lambda函数处理卷释放
release_handler = lambda_.Function(
    self, "ReleaseVolumeHandler",
    runtime=lambda_.Runtime.PYTHON_3_9,
    handler="index.handler",
    code=lambda_.Code.from_inline(release_volume_code)
)
```

### Task 3: 改进缓存清理机制
**优先级：中**

#### 3.1 创建Windows任务计划
```batch
REM 创建定期清理任务
schtasks /create /tn "JenkinsCacheCleanup" /tr "%CACHE_DIR%\cleanup-cache.bat" /sc daily /st 02:00 /ru SYSTEM
```

#### 3.2 改进清理脚本
```batch
@echo off
REM 增强版缓存清理脚本
echo Starting cache cleanup at %date% %time%

REM 清理临时文件（7天前）
if exist "%CACHE_DIR%\temp" (
    forfiles /p "%CACHE_DIR%\temp" /m *.* /d -7 /c "cmd /c del /q @path" 2>nul
)

REM 清理Git缓存中的过期对象
if exist "%CACHE_DIR%\git-cache" (
    for /d %%d in ("%CACHE_DIR%\git-cache\*") do (
        if exist "%%d\.git" (
            cd /d "%%d" && git gc --prune=now 2>nul
        )
    )
)

REM 清理Unity缓存（保留最近30天）
if exist "%CACHE_DIR%\unity-cache" (
    forfiles /p "%CACHE_DIR%\unity-cache" /m *.* /d -30 /c "cmd /c del /q @path" 2>nul
)

echo Cache cleanup completed at %date% %time%
```

## 测试计划

### Phase 1: 单元测试
- [ ] 测试Lambda函数的卷分配逻辑
- [ ] 验证DynamoDB查询和更新操作
- [ ] 测试Windows脚本的磁盘识别

### Phase 2: 集成测试
- [ ] 端到端测试：实例启动到卷挂载
- [ ] 测试实例终止时的卷释放
- [ ] 验证缓存数据的持久性

### Phase 3: 压力测试
- [ ] 并发实例启动测试
- [ ] 卷池耗尽场景测试
- [ ] 异常情况恢复测试

## 实现优先级

### 立即执行（本周）
1. **修复Windows Agent脚本**：解决磁盘识别和挂载问题
2. **测试基本功能**：确保卷能正确分配和挂载

### 短期目标（2周内）
1. **实现生命周期管理**：EC2钩子和SQS处理
2. **完善错误处理**：添加重试和回退机制
3. **基础监控**：CloudWatch指标和告警

### 中期目标（1个月内）
1. **缓存优化**：智能清理和预热
2. **性能调优**：基于实际使用数据优化
3. **运维工具**：管理脚本和仪表板

## 风险缓解

### 高风险项
1. **磁盘识别错误**：可能格式化错误磁盘
   - 缓解：多重验证，大小和设备路径检查
2. **卷状态不一致**：多个实例竞争同一卷
   - 缓解：原子操作和分布式锁

### 中风险项
1. **生命周期钩子超时**：卷释放未完成
   - 缓解：异步处理和状态恢复
2. **缓存数据损坏**：文件系统错误
   - 缓解：定期健康检查和自动修复

## 成功指标

### 技术指标
- 卷分配成功率 > 99%
- 卷挂载时间 < 2分钟
- 缓存命中率 > 70%
- 构建时间减少 > 30%

### 业务指标
- 整体构建成本减少 > 20%
- 开发者满意度提升
- 系统可用性 > 99.5%

## 下一步行动
1. **立即开始**：修复Windows Agent脚本的磁盘识别问题
2. **并行进行**：设计和实现生命周期管理
3. **持续改进**：基于测试结果优化实现