#!/bin/bash

echo "=== Jenkins Master Log Analysis ==="

# 检查可能的Jenkins日志位置
JENKINS_LOGS=(
    "/var/lib/jenkins/logs/jenkins.log"
    "/var/log/jenkins/jenkins.log" 
    "/var/lib/jenkins/jenkins.log"
    "/home/jenkins/jenkins.log"
    "/opt/jenkins/logs/jenkins.log"
)

echo "1. Searching for Jenkins log files:"
for log in "${JENKINS_LOGS[@]}"; do
    if [ -f "$log" ]; then
        echo "Found: $log"
        echo "Last 20 lines:"
        sudo tail -20 "$log"
        echo "---"
    fi
done

# 检查Jenkins进程和日志输出
echo -e "\n2. Jenkins Process and Output:"
sudo ps aux | grep jenkins | grep -v grep
sudo pgrep -f jenkins | xargs -I {} sudo ls -la /proc/{}/fd/ 2>/dev/null | grep log || echo "No log files found in process fd"

# 检查systemd日志
echo -e "\n3. Systemd Jenkins logs:"
sudo journalctl -u jenkins --no-pager -n 30 2>/dev/null || echo "No systemd jenkins logs"

# 检查手动启动的Jenkins日志
echo -e "\n4. Manual Jenkins logs:"
if [ -f "/var/log/jenkins-manual.log" ]; then
    echo "Manual Jenkins log found:"
    sudo tail -20 /var/log/jenkins-manual.log
fi

# 检查EC2 Fleet相关配置和日志
echo -e "\n5. EC2 Fleet Plugin Status:"
curl -s "http://localhost:8080/pluginManager/api/json" | grep -i "ec2-fleet" || echo "Cannot access plugin API"

# 检查Jenkins配置文件
echo -e "\n6. Jenkins Configuration:"
if [ -f "/var/lib/jenkins/config.xml" ]; then
    echo "Jenkins config.xml exists"
    sudo grep -i "fleet\|cloud" /var/lib/jenkins/config.xml 2>/dev/null || echo "No fleet/cloud config found"
fi

# 检查节点状态
echo -e "\n7. Current Nodes:"
curl -s "http://localhost:8080/computer/api/json" | jq '.computer[] | {displayName, offline, temporarilyOffline}' 2>/dev/null || echo "Cannot access computer API"

echo -e "\n=== Analysis Complete ==="