#!/bin/bash

JENKINS_URL="http://54.235.223.176"

echo "=== Jenkins Remote Log Analysis ==="

# 检查Jenkins API访问
echo "1. Testing Jenkins API access:"
curl -s "$JENKINS_URL/api/json" | jq '.mode' 2>/dev/null || echo "Cannot access Jenkins API"

# 检查当前节点状态
echo -e "\n2. Current Jenkins Nodes:"
curl -s "$JENKINS_URL/computer/api/json" | jq '.computer[] | {displayName, offline, temporarilyOffline, labels: .assignedLabels[].name}' 2>/dev/null || echo "Cannot access computer API"

# 检查云配置
echo -e "\n3. Cloud Configuration:"
curl -s "$JENKINS_URL/configureClouds/api/json" 2>/dev/null | jq '.' || echo "Cannot access cloud configuration"

# 检查插件状态
echo -e "\n4. EC2 Fleet Plugin Status:"
curl -s "$JENKINS_URL/pluginManager/api/json" | jq '.plugins[] | select(.shortName | contains("ec2")) | {shortName, version, enabled, active}' 2>/dev/null || echo "Cannot access plugin API"

# 检查系统日志
echo -e "\n5. Jenkins System Log (if accessible):"
curl -s "$JENKINS_URL/log/all" 2>/dev/null | tail -20 || echo "Cannot access system log"

# 检查构建队列
echo -e "\n6. Build Queue:"
curl -s "$JENKINS_URL/queue/api/json" | jq '.items[] | {task: .task.name, why: .why}' 2>/dev/null || echo "No items in queue or cannot access"

echo -e "\n=== Remote Analysis Complete ==="