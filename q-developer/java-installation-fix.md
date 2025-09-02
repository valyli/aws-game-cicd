# Java 安装问题修复

## 问题描述

Jenkins Agent 启动时 Java 安装经常失败，导致 Agent 无法运行。

## 根本原因

1. **包冲突**：curl 包版本冲突导致安装失败
2. **验证不足**：Java 安装后没有充分验证
3. **重试机制缺失**：安装失败后没有重试机制

## 修复方案

### 1. 使用 --allowerasing 参数
```bash
# 解决包冲突问题
yum install -y java-17-amazon-corretto --allowerasing
```

### 2. 添加重试机制
```bash
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
```

### 3. 完整验证
```bash
# 设置 JAVA_HOME
JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:bin/java::")
export JAVA_HOME
echo "JAVA_HOME=$JAVA_HOME" >> /etc/environment

# 最终验证
java -version
echo "JAVA_HOME: $JAVA_HOME"
```

## 验证步骤

1. 检查 Java 版本：`java -version`
2. 检查 JAVA_HOME：`echo $JAVA_HOME`
3. 测试 jar 运行：`java -help`

## 已修复的文件

- `jenkins_agent_stack.py` - 添加了 Java 安装重试和验证机制