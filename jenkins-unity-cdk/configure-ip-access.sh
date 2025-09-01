#!/bin/bash

echo "🔒 配置Jenkins访问IP地址范围"
echo "=========================="

# 获取当前公网IP
echo "1. 检测当前公网IP..."
CURRENT_IP=$(curl -s https://checkip.amazonaws.com)
if [ ! -z "$CURRENT_IP" ]; then
    echo "当前公网IP: $CURRENT_IP"
    CURRENT_CIDR="$CURRENT_IP/32"
else
    echo "无法检测当前IP"
    CURRENT_CIDR=""
fi

echo ""
echo "2. 当前配置的允许IP范围:"
grep -A 10 "allowed_cidrs:" config/default.yaml

echo ""
echo "3. 选择配置方式:"
echo "a) 添加当前IP ($CURRENT_IP/32)"
echo "b) 手动输入IP范围"
echo "c) 查看当前配置"
echo "d) 退出"

read -p "请选择 (a/b/c/d): " choice

case $choice in
    a)
        if [ ! -z "$CURRENT_CIDR" ]; then
            echo "添加当前IP: $CURRENT_CIDR"
            # 在allowed_cidrs下添加当前IP
            sed -i "/allowed_cidrs:/a\\  - \"$CURRENT_CIDR\"  # 当前IP $(date)" config/default.yaml
            echo "✅ 已添加当前IP到配置文件"
        else
            echo "❌ 无法获取当前IP"
        fi
        ;;
    b)
        echo "请输入允许的IP地址范围 (CIDR格式，如 203.0.113.0/24):"
        read -p "IP范围: " USER_CIDR
        if [[ $USER_CIDR =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]]; then
            sed -i "/allowed_cidrs:/a\\  - \"$USER_CIDR\"  # 用户添加 $(date)" config/default.yaml
            echo "✅ 已添加 $USER_CIDR 到配置文件"
        else
            echo "❌ IP地址格式不正确"
        fi
        ;;
    c)
        echo "当前完整配置:"
        cat config/default.yaml
        ;;
    d)
        echo "退出"
        exit 0
        ;;
    *)
        echo "❌ 无效选择"
        ;;
esac

echo ""
echo "📋 下一步:"
echo "1. 检查配置文件: cat config/default.yaml"
echo "2. 部署更新: cdk deploy unity-cicd-vpc-stack --require-approval never"
echo "3. 验证访问: curl -I http://your-alb-url:8080"

echo ""
echo "⚠️  安全提醒:"
echo "- 避免使用 0.0.0.0/0 (允许所有IP)"
echo "- 定期审查和更新IP地址范围"
echo "- 考虑使用VPN或堡垒机进一步提高安全性"