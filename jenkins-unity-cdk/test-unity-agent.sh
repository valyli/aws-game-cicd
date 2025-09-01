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
