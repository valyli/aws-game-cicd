#!/bin/bash

echo "=== Jenkins Log Analysis ==="

# 检查Jenkins主日志
echo "1. Jenkins Main Log (last 50 lines):"
sudo tail -50 /var/log/jenkins/jenkins.log 2>/dev/null || echo "Jenkins log not found at /var/log/jenkins/jenkins.log"

# 检查系统日志中的Jenkins相关信息
echo -e "\n2. System Log - Jenkins related:"
sudo journalctl -u jenkins --no-pager -n 20 2>/dev/null || echo "No systemd jenkins service logs"

# 检查EC2 Fleet Plugin相关日志
echo -e "\n3. Searching for EC2 Fleet Plugin logs:"
sudo grep -i "ec2.*fleet\|fleet.*ec2" /var/log/jenkins/jenkins.log 2>/dev/null | tail -10 || echo "No EC2 Fleet logs found"

# 检查节点连接日志
echo -e "\n4. Node connection logs:"
sudo grep -i "node\|agent\|slave" /var/log/jenkins/jenkins.log 2>/dev/null | tail -10 || echo "No node connection logs found"

# 检查当前Jenkins进程
echo -e "\n5. Jenkins Process Status:"
ps aux | grep jenkins | grep -v grep

# 检查端口监听
echo -e "\n6. Jenkins Port Status:"
netstat -tlnp | grep :8080

# 检查Jenkins配置目录
echo -e "\n7. Jenkins Home Directory:"
ls -la /var/lib/jenkins/ 2>/dev/null | head -10 || echo "Jenkins home not accessible"

echo -e "\n=== Log Check Complete ==="