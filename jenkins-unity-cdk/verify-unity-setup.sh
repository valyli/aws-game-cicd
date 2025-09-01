#!/bin/bash

echo "🔍 Unity CI/CD 验证脚本"
echo "======================"

# 1. 验证所有栈部署状态
echo "1. 检查栈部署状态..."
STACKS=("unity-cicd-vpc-stack" "unity-cicd-storage-stack" "unity-cicd-iam-stack" 
        "unity-cicd-lambda-stack" "unity-cicd-jenkins-master-stack" "unity-cicd-jenkins-agent-stack")

for STACK in "${STACKS[@]}"; do
    STATUS=$(aws cloudformation describe-stacks --stack-name $STACK --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")
    if [ "$STATUS" = "CREATE_COMPLETE" ] || [ "$STATUS" = "UPDATE_COMPLETE" ]; then
        echo "✅ $STACK: $STATUS"
    else
        echo "❌ $STACK: $STATUS"
    fi
done

# 2. 检查Jenkins Master状态
echo ""
echo "2. 检查Jenkins Master状态..."
JENKINS_INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
    --auto-scaling-group-names unity-cicd-jenkins-master-asg \
    --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
    --output text 2>/dev/null)

if [ "$JENKINS_INSTANCE_ID" != "None" ] && [ ! -z "$JENKINS_INSTANCE_ID" ]; then
    echo "✅ Jenkins Master实例: $JENKINS_INSTANCE_ID"
    
    # 获取Jenkins URL
    JENKINS_URL=$(aws cloudformation describe-stacks \
        --stack-name unity-cicd-jenkins-master-stack \
        --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
        --output text)
    echo "🌐 Jenkins URL: ${JENKINS_URL}:8080"
else
    echo "❌ Jenkins Master实例未找到"
fi

# 3. 检查Agent ASG配置
echo ""
echo "3. 检查Jenkins Agent ASG配置..."
AGENT_ASG_STATUS=$(aws autoscaling describe-auto-scaling-groups \
    --auto-scaling-group-names unity-cicd-jenkins-agent-asg \
    --query 'AutoScalingGroups[0].{MinSize:MinSize,MaxSize:MaxSize,DesiredCapacity:DesiredCapacity}' \
    --output table 2>/dev/null)

if [ $? -eq 0 ]; then
    echo "✅ Jenkins Agent ASG配置:"
    echo "$AGENT_ASG_STATUS"
else
    echo "❌ Jenkins Agent ASG未找到"
fi

# 4. 检查Lambda函数
echo ""
echo "4. 检查Lambda函数..."
LAMBDA_FUNCTIONS=("unity-cicd-allocate-cache-volume" "unity-cicd-release-cache-volume" "unity-cicd-maintain-cache-pool")

for FUNC in "${LAMBDA_FUNCTIONS[@]}"; do
    STATUS=$(aws lambda get-function --function-name $FUNC --query 'Configuration.State' --output text 2>/dev/null || echo "NOT_FOUND")
    if [ "$STATUS" = "Active" ]; then
        echo "✅ $FUNC: $STATUS"
    else
        echo "❌ $FUNC: $STATUS"
    fi
done

# 5. 检查Unity许可证配置
echo ""
echo "5. 检查Unity许可证配置..."
UNITY_PARAMS=("/jenkins/unity/username" "/jenkins/unity/password" "/jenkins/unity/serial")
UNITY_CONFIGURED=true

for PARAM in "${UNITY_PARAMS[@]}"; do
    if aws ssm get-parameter --name "$PARAM" --with-decryption >/dev/null 2>&1; then
        echo "✅ $PARAM: 已配置"
    else
        echo "❌ $PARAM: 未配置"
        UNITY_CONFIGURED=false
    fi
done

# 6. 生成下一步建议
echo ""
echo "📋 下一步建议:"
echo "=============="

if [ "$UNITY_CONFIGURED" = false ]; then
    echo "⚠️  需要配置Unity许可证:"
    echo "   aws ssm put-parameter --name '/jenkins/unity/username' --value 'your-username' --type 'SecureString'"
    echo "   aws ssm put-parameter --name '/jenkins/unity/password' --value 'your-password' --type 'SecureString'"
    echo "   aws ssm put-parameter --name '/jenkins/unity/serial' --value 'your-serial' --type 'SecureString'"
    echo ""
fi

echo "1. 访问Jenkins: ${JENKINS_URL}:8080"
echo "2. 完成Jenkins初始设置（如果还没完成）"
echo "3. 安装必需插件: EC2, Git, Pipeline"
echo "4. 配置EC2 Cloud连接到Unity Agent"
echo "5. 创建Unity项目和Pipeline任务"
echo ""
echo "详细步骤请参考: ./UNITY_DEMO_GUIDE.md"

# 7. 创建快速测试脚本
echo ""
echo "🚀 创建快速测试脚本..."
cat > test-unity-agent.sh << 'EOF'
#!/bin/bash
echo "测试Unity Agent连接..."

# 手动启动一个Agent实例进行测试
aws autoscaling set-desired-capacity \
    --auto-scaling-group-name unity-cicd-jenkins-agent-asg \
    --desired-capacity 1

echo "等待Agent实例启动..."
sleep 60

# 检查实例状态
aws autoscaling describe-auto-scaling-groups \
    --auto-scaling-group-names unity-cicd-jenkins-agent-asg \
    --query 'AutoScalingGroups[0].Instances[*].{InstanceId:InstanceId,State:LifecycleState,Health:HealthStatus}'

echo "Agent测试完成。记得在测试后将desired-capacity设回0以节省成本。"
EOF

chmod +x test-unity-agent.sh
echo "✅ 创建了测试脚本: ./test-unity-agent.sh"

echo ""
echo "🎉 验证完成！"