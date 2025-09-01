#!/bin/bash

set -e

echo "🔍 Unity AMI 验证脚本"
echo "==================="

if [ -z "$1" ]; then
    echo "用法: $0 <AMI_ID>"
    echo "示例: $0 ami-1234567890abcdef0"
    exit 1
fi

AMI_ID=$1
SECURITY_GROUP="sg-0cae1c773589f67ba"
SUBNET_ID="subnet-02ac9ed0cfe66207b"
IAM_ROLE="unity-cicd-jenkins-agent-role"

echo "验证AMI: $AMI_ID"

# 启动测试实例
echo "1. 启动测试实例..."
TEST_INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --instance-type c5.large \
    --security-group-ids $SECURITY_GROUP \
    --subnet-id $SUBNET_ID \
    --iam-instance-profile Name=$IAM_ROLE \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=unity-ami-test},{Key=Purpose,Value=AMI-Verification}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "✅ 测试实例启动: $TEST_INSTANCE_ID"

# 等待实例运行
echo "2. 等待实例启动..."
aws ec2 wait instance-running --instance-ids $TEST_INSTANCE_ID
echo "✅ 实例正在运行"

# 等待SSM Agent就绪
echo "3. 等待SSM Agent就绪..."
sleep 60

# 验证Unity安装
echo "4. 验证Unity安装..."
COMMAND_ID=$(aws ssm send-command \
    --instance-ids $TEST_INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "echo === Unity验证测试 ===",
        "echo 1. 检查Unity文件:",
        "ls -la /opt/unity/Editor/Unity 2>/dev/null || echo Unity文件不存在",
        "echo",
        "echo 2. 检查Unity版本:",
        "/opt/unity/Editor/Unity -version 2>/dev/null || echo Unity版本检查失败",
        "echo",
        "echo 3. 检查符号链接:",
        "ls -la /usr/local/bin/unity 2>/dev/null || echo 符号链接不存在",
        "echo",
        "echo 4. 检查Java:",
        "java -version 2>&1 | head -1",
        "echo",
        "echo 5. 检查Docker:",
        "docker --version 2>/dev/null || echo Docker未安装",
        "echo",
        "echo 6. 检查AWS CLI:",
        "aws --version 2>/dev/null || echo AWS CLI未安装",
        "echo",
        "echo 7. 检查Android SDK:",
        "ls -la /opt/android-sdk/ 2>/dev/null || echo Android SDK未安装",
        "echo",
        "echo 8. 检查磁盘空间:",
        "df -h /",
        "echo",
        "echo === 验证完成 ==="
    ]' \
    --query 'Command.CommandId' \
    --output text)

echo "等待验证命令执行..."
sleep 10

# 获取验证结果
echo "5. 获取验证结果..."
VERIFICATION_RESULT=$(aws ssm get-command-invocation \
    --command-id $COMMAND_ID \
    --instance-id $TEST_INSTANCE_ID \
    --query 'StandardOutputContent' \
    --output text)

echo "$VERIFICATION_RESULT"

# 检查验证是否成功
if echo "$VERIFICATION_RESULT" | grep -q "Unity 2023.2.20f1"; then
    echo ""
    echo "✅ AMI验证成功！"
    echo "AMI ID: $AMI_ID"
    echo "Unity版本: $(echo "$VERIFICATION_RESULT" | grep "Unity 2023" | head -1)"
    
    # 生成配置更新命令
    echo ""
    echo "📝 更新配置文件："
    echo "sed -i 's/ami-[a-z0-9]*/$AMI_ID/g' config/default.yaml"
    
    # 保存验证通过的AMI ID
    echo $AMI_ID > .verified-unity-ami-id
    echo "💾 已验证的AMI ID保存到: .verified-unity-ami-id"
    
else
    echo ""
    echo "❌ AMI验证失败！"
    echo "Unity未正确安装或配置"
fi

# 清理测试实例
echo ""
echo "6. 清理测试实例..."
aws ec2 terminate-instances --instance-ids $TEST_INSTANCE_ID
echo "✅ 测试实例已终止: $TEST_INSTANCE_ID"

echo ""
echo "🎯 验证完成！"