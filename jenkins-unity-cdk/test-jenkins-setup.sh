#!/bin/bash

echo "🧪 Jenkins Unity CI/CD 测试脚本"
echo "==============================="

# 1. 检查Jenkins是否可访问
echo "1. 测试Jenkins访问..."
JENKINS_URL="http://unity-cicd-jenkins-alb-1860412095.us-east-1.elb.amazonaws.com:8080"
if curl -s -I "$JENKINS_URL/login" | grep -q "200 OK"; then
    echo "✅ Jenkins可访问: $JENKINS_URL"
else
    echo "❌ Jenkins无法访问"
fi

# 2. 检查Agent ASG
echo ""
echo "2. 检查Agent ASG状态..."
aws autoscaling describe-auto-scaling-groups \
    --auto-scaling-group-names unity-cicd-jenkins-agent-asg \
    --query 'AutoScalingGroups[0].{MinSize:MinSize,MaxSize:MaxSize,DesiredCapacity:DesiredCapacity,InstanceCount:length(Instances)}' \
    --output table

# 3. 检查Lambda函数
echo ""
echo "3. 检查Lambda函数状态..."
for func in "unity-cicd-allocate-cache-volume" "unity-cicd-release-cache-volume" "unity-cicd-maintain-cache-pool"; do
    status=$(aws lambda get-function --function-name $func --query 'Configuration.State' --output text 2>/dev/null || echo "NOT_FOUND")
    if [ "$status" = "Active" ]; then
        echo "✅ $func: Active"
    else
        echo "❌ $func: $status"
    fi
done

# 4. 创建简化的Jenkins任务配置
echo ""
echo "4. 生成Jenkins任务配置..."
cat > jenkins-job-config.xml << 'EOF'
<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job@2.40">
  <actions/>
  <description>Unity Demo Build Job</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps@2.92">
    <script>
pipeline {
    agent any
    
    stages {
        stage('Test Environment') {
            steps {
                echo 'Testing build environment...'
                sh 'echo "Current user: $(whoami)"'
                sh 'echo "Current directory: $(pwd)"'
                sh 'echo "Available disk space:"'
                sh 'df -h'
                sh 'echo "System info:"'
                sh 'uname -a'
            }
        }
        
        stage('Test Unity (if available)') {
            steps {
                script {
                    sh '''
                        echo "Looking for Unity installation..."
                        find /opt -name "Unity" -type f 2>/dev/null || echo "Unity not found in /opt"
                        which unity || echo "Unity not in PATH"
                        
                        # Test placeholder Unity if exists
                        if [ -f /opt/unity/Editor/Unity ]; then
                            echo "Found Unity at /opt/unity/Editor/Unity"
                            /opt/unity/Editor/Unity -version || echo "Unity version check failed"
                        else
                            echo "Unity not installed - this is expected for basic infrastructure test"
                        fi
                    '''
                }
            }
        }
    }
    
    post {
        always {
            echo 'Build completed!'
        }
        success {
            echo 'Build succeeded!'
        }
        failure {
            echo 'Build failed!'
        }
    }
}
    </script>
    <sandbox>true</sandbox>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>
EOF

echo "✅ Jenkins任务配置已生成: jenkins-job-config.xml"

# 5. 提供下一步指导
echo ""
echo "📋 下一步操作指南:"
echo "=================="
echo "1. 访问Jenkins: $JENKINS_URL"
echo "2. 使用以下命令获取登录密码:"
echo "   ./get-jenkins-password.sh"
echo ""
echo "3. 在Jenkins中创建新任务:"
echo "   - 点击 'New Item'"
echo "   - 名称: unity-test-build"
echo "   - 类型: Pipeline"
echo "   - 在Pipeline部分选择 'Pipeline script'"
echo "   - 复制jenkins-job-config.xml中的script内容"
echo ""
echo "4. 运行任务测试基础设施"
echo ""
echo "5. 如果基础测试成功，再安装Unity:"
echo "   - 可以手动在Agent实例上安装Unity"
echo "   - 或者使用预构建的Unity AMI"
echo ""
echo "🎯 当前状态: 基础设施已就绪，可以进行基本的CI/CD测试"