#!/bin/bash

set -e

echo "🏗️ Unity Agent AMI 构建器"
echo "======================="

# 配置变量
BASE_AMI="ami-0abcdef1234567890"  # Amazon Linux 2023
INSTANCE_TYPE="c5.xlarge"
# 使用SSM连接，不需要密钥对
SECURITY_GROUP="sg-0cae1c773589f67ba"  # Jenkins Agent安全组
SUBNET_ID="subnet-02ac9ed0cfe66207b"   # 私有子网
IAM_ROLE="unity-cicd-jenkins-agent-instance-profile"

# 获取最新的Amazon Linux 2023 AMI
echo "1. 获取最新的Amazon Linux 2023 AMI..."
BASE_AMI=$(aws ec2 describe-images \
    --owners amazon \
    --filters "Name=name,Values=al2023-ami-*" "Name=architecture,Values=x86_64" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text)

echo "使用基础AMI: $BASE_AMI"

# 启动临时实例
echo "2. 启动临时实例进行Unity安装..."
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $BASE_AMI \
    --instance-type $INSTANCE_TYPE \
    --security-group-ids $SECURITY_GROUP \
    --subnet-id $SUBNET_ID \
    --iam-instance-profile Name=$IAM_ROLE \
    --user-data file://scripts/unity-install.sh \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=unity-ami-builder},{Key=Purpose,Value=AMI-Build}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "✅ 实例已启动: $INSTANCE_ID"

# 等待实例运行
echo "3. 等待实例启动..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID
echo "✅ 实例正在运行"

# 等待Unity安装完成
echo "4. 等待Unity安装完成（预计30-45分钟）..."
echo "您可以通过以下命令监控安装进度："
echo "aws ssm send-command --instance-ids $INSTANCE_ID --document-name 'AWS-RunShellScript' --parameters 'commands=[\"tail -f /var/log/user-data.log\"]'"

# 提供监控脚本
cat > monitor-unity-install.sh << EOF
#!/bin/bash
echo "监控Unity安装进度..."
while true; do
    # 检查Unity是否安装完成
    RESULT=\$(aws ssm send-command \
        --instance-ids $INSTANCE_ID \
        --document-name "AWS-RunShellScript" \
        --parameters 'commands=["test -f /opt/unity/Editor/Unity && echo INSTALLED || echo INSTALLING"]' \
        --query 'Command.CommandId' \
        --output text 2>/dev/null)
    
    if [ ! -z "\$RESULT" ]; then
        sleep 5
        STATUS=\$(aws ssm get-command-invocation \
            --command-id \$RESULT \
            --instance-id $INSTANCE_ID \
            --query 'StandardOutputContent' \
            --output text 2>/dev/null | tr -d '\n')
        
        echo "\$(date): Unity安装状态: \$STATUS"
        
        if [ "\$STATUS" = "INSTALLED" ]; then
            echo "✅ Unity安装完成！"
            break
        fi
    fi
    
    sleep 60
done
EOF

chmod +x monitor-unity-install.sh
echo "✅ 监控脚本已创建: ./monitor-unity-install.sh"

# 等待用户确认
echo ""
echo "📋 下一步操作："
echo "1. 运行 ./monitor-unity-install.sh 监控安装进度"
echo "2. 安装完成后，运行以下命令创建AMI："
echo ""
echo "# 验证Unity安装"
echo "aws ssm send-command --instance-ids $INSTANCE_ID --document-name 'AWS-RunShellScript' --parameters 'commands=[\"/opt/unity/Editor/Unity -version\"]'"
echo ""
echo "# 创建AMI"
echo "AMI_ID=\$(aws ec2 create-image --instance-id $INSTANCE_ID --name 'unity-agent-\$(date +%Y%m%d-%H%M)' --description 'Unity Agent with Unity 2023.2.20f1 and Android SDK' --query 'ImageId' --output text)"
echo "echo \"AMI创建中: \$AMI_ID\""
echo ""
echo "# 等待AMI创建完成"
echo "aws ec2 wait image-available --image-ids \$AMI_ID"
echo "echo \"✅ AMI创建完成: \$AMI_ID\""
echo ""
echo "# 清理临时实例"
echo "aws ec2 terminate-instances --instance-ids $INSTANCE_ID"
echo ""
echo "# 更新配置文件"
echo "sed -i 's/ami-[a-z0-9]*/'\$AMI_ID'/g' config/default.yaml"

# 保存实例ID供后续使用
echo $INSTANCE_ID > .unity-ami-instance-id
echo ""
echo "💾 实例ID已保存到 .unity-ami-instance-id"