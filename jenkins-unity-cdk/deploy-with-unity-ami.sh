#!/bin/bash

set -e

echo "🚀 Unity CI/CD 完整部署流程"
echo "=========================="

# 检查是否有已验证的AMI
if [ -f .verified-unity-ami-id ]; then
    UNITY_AMI_ID=$(cat .verified-unity-ami-id)
    echo "✅ 发现已验证的Unity AMI: $UNITY_AMI_ID"
    
    # 更新配置文件
    echo "📝 更新配置文件..."
    if grep -q "unity_ami_id" config/default.yaml; then
        sed -i "s/unity_ami_id:.*/unity_ami_id: \"$UNITY_AMI_ID\"/" config/default.yaml
    else
        echo "unity_ami_id: \"$UNITY_AMI_ID\"" >> config/default.yaml
    fi
    
    echo "✅ 配置文件已更新"
else
    echo "⚠️  未找到已验证的Unity AMI"
    echo "请先运行以下步骤："
    echo "1. chmod +x build-unity-ami.sh && ./build-unity-ami.sh"
    echo "2. 等待AMI构建完成"
    echo "3. ./verify-unity-ami.sh <AMI_ID>"
    echo "4. 再次运行此脚本"
    exit 1
fi

# 部署基础设施
echo ""
echo "🏗️ 部署Jenkins基础设施..."
source .venv/bin/activate

# 部署所有栈
echo "部署VPC、存储、IAM栈..."
cdk deploy unity-cicd-vpc-stack unity-cicd-storage-stack unity-cicd-iam-stack --require-approval never

echo "部署Lambda栈..."
cdk deploy unity-cicd-lambda-stack --require-approval never

echo "部署Jenkins Master栈..."
cdk deploy unity-cicd-jenkins-master-stack --require-approval never

echo "部署Jenkins Agent栈（使用Unity AMI）..."
cdk deploy unity-cicd-jenkins-agent-stack --require-approval never

# 验证部署
echo ""
echo "🔍 验证部署..."
./verify-unity-setup.sh

# 获取Jenkins信息
echo ""
echo "🎯 部署完成！"
echo "============="

JENKINS_URL=$(aws cloudformation describe-stacks \
    --stack-name unity-cicd-jenkins-master-stack \
    --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
    --output text)

echo "Jenkins URL: ${JENKINS_URL}:8080"
echo "Unity AMI: $UNITY_AMI_ID"

echo ""
echo "📋 下一步："
echo "1. 获取Jenkins密码: ./get-jenkins-password.sh"
echo "2. 访问Jenkins并完成初始设置"
echo "3. 配置EC2 Cloud使用Unity Agent"
echo "4. 创建Unity构建任务"
echo ""
echo "🎮 Unity Agent已预装Unity 2023.2.20f1，可直接用于构建！"