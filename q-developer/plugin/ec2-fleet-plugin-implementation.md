# EC2 Fleet Plugin 实现方案

## 基于 EC2 Fleet Plugin 的实现

参考开源项目：[jenkinsci/ec2-fleet-plugin](https://github.com/jenkinsci/ec2-fleet-plugin)

## EC2 Fleet Plugin vs EC2 Plugin 对比

### EC2 Fleet Plugin 优势
```yaml
成本优化:
  - 原生支持 EC2 Fleet (Spot + On-Demand 混合)
  - 更好的 Spot 实例管理
  - 自动故障转移

扩展性:
  - 支持更大规模的 Agent 集群
  - 更高效的实例管理
  - 更好的负载均衡

稳定性:
  - 专门为 Fleet 设计
  - 更好的 Spot 中断处理
  - 自动实例替换
```

## 实现架构

### 1. 整体架构
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Jenkins       │    │   EC2 Fleet      │    │   Agent         │
│   Master        │    │   (Auto Scaling) │    │   Instances     │
│                 │    │                  │    │                 │
│ Fleet Plugin    │───▶│ Launch Template  │───▶│ Unity Build Env │
│ Configuration   │    │ Spot + On-Demand │    │ Auto Connect    │
│                 │    │ Multi-AZ         │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 2. 核心组件

#### 2.1 EC2 Fleet 配置
```json
{
  "LaunchTemplateConfigs": [
    {
      "LaunchTemplateSpecification": {
        "LaunchTemplateName": "unity-build-agent-template",
        "Version": "$Latest"
      },
      "Overrides": [
        {
          "InstanceType": "c5.large",
          "SubnetId": "subnet-12345678",
          "AvailabilityZone": "us-east-1a"
        },
        {
          "InstanceType": "c5.xlarge",
          "SubnetId": "subnet-87654321",
          "AvailabilityZone": "us-east-1b"
        }
      ]
    }
  ],
  "TargetCapacitySpecification": {
    "TotalTargetCapacity": 10,
    "OnDemandTargetCapacity": 2,
    "SpotTargetCapacity": 8,
    "DefaultTargetCapacityType": "spot"
  },
  "SpotOptions": {
    "AllocationStrategy": "diversified",
    "InstanceInterruptionBehavior": "terminate",
    "InstancePoolsToUseCount": 3
  },
  "OnDemandOptions": {
    "AllocationStrategy": "lowest-price"
  },
  "Type": "maintain",
  "ReplaceUnhealthyInstances": true
}
```

#### 2.2 Launch Template
```yaml
LaunchTemplate:
  LaunchTemplateName: unity-build-agent-template
  LaunchTemplateData:
    ImageId: ami-unity-build-env  # 预装 Unity 的 AMI
    InstanceType: c5.large
    SecurityGroupIds:
      - sg-jenkins-agent
    IamInstanceProfile:
      Name: jenkins-agent-profile
    UserData: |
      #!/bin/bash
      # Base64 编码的启动脚本
      IyEvYmluL2Jhc2gKIyBBZ2VudCDoh6rliqjov57mjqXohJrmnac=
    TagSpecifications:
      - ResourceType: instance
        Tags:
          - Key: Name
            Value: unity-build-agent
          - Key: Environment
            Value: production
          - Key: ManagedBy
            Value: jenkins-fleet-plugin
```

## 详细实现步骤

### 阶段 1: CDK 基础设施

#### 1.1 Fleet 配置 Stack
```python
class EC2FleetStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # 创建 Launch Template
        self.launch_template = self._create_launch_template()
        
        # 创建 EC2 Fleet
        self.ec2_fleet = self._create_ec2_fleet()
        
        # 输出 Fleet ID 供 Jenkins 使用
        self._create_outputs()
    
    def _create_launch_template(self):
        # User Data 脚本
        user_data_script = self._build_user_data_script()
        
        return ec2.LaunchTemplate(
            self, "UnityBuildAgentTemplate",
            launch_template_name="unity-build-agent-template",
            machine_image=ec2.MachineImage.lookup(
                name="unity-build-env-*",
                owners=["self"]
            ),
            instance_type=ec2.InstanceType("c5.large"),
            security_group=self.agent_security_group,
            role=self.agent_role,
            user_data=ec2.UserData.custom(user_data_script),
            require_imdsv2=True
        )
    
    def _create_ec2_fleet(self):
        return ec2.CfnEC2Fleet(
            self, "UnityBuildFleet",
            launch_template_configs=[{
                "launchTemplateSpecification": {
                    "launchTemplateId": self.launch_template.launch_template_id,
                    "version": "$Latest"
                },
                "overrides": [
                    {
                        "instanceType": "c5.large",
                        "subnetId": subnet.subnet_id,
                        "availabilityZone": subnet.availability_zone
                    }
                    for subnet in self.private_subnets
                ]
            }],
            target_capacity_specification={
                "totalTargetCapacity": 10,
                "onDemandTargetCapacity": 2,
                "spotTargetCapacity": 8,
                "defaultTargetCapacityType": "spot"
            },
            spot_options={
                "allocationStrategy": "diversified",
                "instanceInterruptionBehavior": "terminate",
                "instancePoolsToUseCount": 3
            },
            type="maintain",
            replace_unhealthy_instances=True
        )
```

#### 1.2 User Data 脚本
```bash
#!/bin/bash
# unity-agent-userdata.sh

set -e
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "Starting Unity Build Agent setup..."

# 获取实例信息
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -s)
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id)
PRIVATE_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/local-ipv4)

echo "Instance ID: $INSTANCE_ID"
echo "Private IP: $PRIVATE_IP"

# 获取 Jenkins Master 信息
JENKINS_URL=$(aws ssm get-parameter --name "/jenkins/master/url" --region us-east-1 --query 'Parameter.Value' --output text)
echo "Jenkins URL: $JENKINS_URL"

# 等待 Jenkins Master 可用
echo "Waiting for Jenkins Master..."
for i in {1..30}; do
    if curl -s "$JENKINS_URL/login" > /dev/null 2>&1; then
        echo "Jenkins Master is ready"
        break
    fi
    echo "Attempt $i/30: Jenkins not ready, waiting..."
    sleep 10
done

# 创建工作目录
mkdir -p /opt/jenkins
chown jenkins:jenkins /opt/jenkins
cd /opt/jenkins

# 下载 Jenkins Agent JAR
echo "Downloading Jenkins Agent JAR..."
sudo -u jenkins curl -o agent.jar "$JENKINS_URL/jnlpJars/agent.jar"

# 启动 Jenkins Agent
echo "Starting Jenkins Agent..."
sudo -u jenkins nohup java -jar agent.jar \
    -jnlpUrl "$JENKINS_URL/computer/$INSTANCE_ID/jenkins-agent.jnlp" \
    -workDir "/opt/jenkins" \
    > agent.log 2>&1 &

echo "Jenkins Agent started successfully"

# 设置健康检查
cat > /opt/jenkins/health-check.sh << 'EOF'
#!/bin/bash
# 检查 Agent 进程是否运行
if pgrep -f "agent.jar" > /dev/null; then
    echo "Agent is running"
    exit 0
else
    echo "Agent is not running"
    exit 1
fi
EOF

chmod +x /opt/jenkins/health-check.sh

# 设置定时健康检查
echo "*/1 * * * * /opt/jenkins/health-check.sh" | crontab -u jenkins -

echo "Unity Build Agent setup completed"
```

### 阶段 2: Jenkins 配置

#### 2.1 JCasC 配置
```yaml
# configs/jenkins.yaml
jenkins:
  systemMessage: "Unity CI/CD with EC2 Fleet Plugin"
  numExecutors: 0
  mode: EXCLUSIVE
  
  clouds:
    - ec2Fleet:
        name: "unity-build-fleet"
        awsCredentialsId: ""  # 使用 IAM 角色
        region: "us-east-1"
        fleet: "${EC2_FLEET_ID}"  # 从 SSM 参数获取
        labelString: "unity linux build"
        idleMinutes: 10
        minSize: 0
        maxSize: 20
        numExecutors: 2
        addNodeOnlyIfRunning: true
        restrictUsage: false
        scaleExecutorsByWeight: true
        initOnlineTimeoutSec: 300
        initOnlineCheckIntervalSec: 15
        cloudStatusIntervalSec: 10
        disableTaskResubmit: false
        noDelayProvision: false

security:
  globalJobDslSecurityConfiguration:
    useScriptSecurity: false

unclassified:
  location:
    adminAddress: "admin@company.com"
    url: "${JENKINS_URL}"
```

#### 2.2 Plugin 安装配置
```txt
# configs/plugins.txt
ec2-fleet:1.10.0
configuration-as-code:1.55
workflow-aggregator:2.6
git:4.8.3
pipeline-stage-view:2.25
blueocean:1.25.2
unity3d-plugin:1.4
android-emulator:3.1
```

### 阶段 3: Unity 构建环境

#### 3.1 AMI 构建脚本
```bash
#!/bin/bash
# build-unity-ami.sh

set -e

echo "Building Unity Build Agent AMI..."

# 启动基础实例
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id ami-0abcdef1234567890 \
    --instance-type t3.medium \
    --key-name jenkins-key \
    --security-group-ids sg-12345678 \
    --subnet-id subnet-12345678 \
    --iam-instance-profile Name=jenkins-agent-profile \
    --user-data file://ami-setup-script.sh \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=unity-ami-builder}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "Launched AMI builder instance: $INSTANCE_ID"

# 等待实例运行
aws ec2 wait instance-running --instance-ids $INSTANCE_ID
echo "Instance is running"

# 等待软件安装完成 (通过 SSM 检查)
echo "Waiting for software installation..."
for i in {1..60}; do
    STATUS=$(aws ssm send-command \
        --instance-ids $INSTANCE_ID \
        --document-name "AWS-RunShellScript" \
        --parameters 'commands=["test -f /tmp/setup-complete && echo READY || echo INSTALLING"]' \
        --query 'Command.CommandId' \
        --output text)
    
    sleep 10
    
    RESULT=$(aws ssm get-command-invocation \
        --command-id $STATUS \
        --instance-id $INSTANCE_ID \
        --query 'StandardOutputContent' \
        --output text 2>/dev/null || echo "INSTALLING")
    
    if [[ "$RESULT" == "READY" ]]; then
        echo "Software installation completed"
        break
    fi
    
    echo "Installation in progress... ($i/60)"
    sleep 50
done

# 创建 AMI
AMI_ID=$(aws ec2 create-image \
    --instance-id $INSTANCE_ID \
    --name "unity-build-agent-$(date +%Y%m%d-%H%M%S)" \
    --description "Unity Build Agent with Java 17, Unity 2022.3, Docker" \
    --no-reboot \
    --query 'ImageId' \
    --output text)

echo "Created AMI: $AMI_ID"

# 等待 AMI 可用
aws ec2 wait image-available --image-ids $AMI_ID
echo "AMI is available"

# 更新 SSM 参数
aws ssm put-parameter \
    --name "/jenkins/agent/ami-id" \
    --value $AMI_ID \
    --type String \
    --overwrite

# 清理构建实例
aws ec2 terminate-instances --instance-ids $INSTANCE_ID
echo "Cleaned up builder instance"

echo "Unity AMI build completed: $AMI_ID"
```

#### 3.2 AMI 设置脚本
```bash
#!/bin/bash
# ami-setup-script.sh

set -e
exec > >(tee /var/log/ami-setup.log|logger -t ami-setup -s 2>/dev/console) 2>&1

echo "Starting Unity Build Agent AMI setup..."

# 更新系统
yum update -y

# 安装基础软件
yum install -y \
    java-17-amazon-corretto \
    git \
    docker \
    wget \
    curl \
    unzip \
    htop \
    amazon-ssm-agent

# 启动服务
systemctl enable docker
systemctl start docker
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# 创建 jenkins 用户
useradd -m -s /bin/bash jenkins
usermod -aG docker jenkins

# 安装 Unity Hub
echo "Installing Unity Hub..."
wget -qO - https://hub.unity3d.com/linux/keys/public | apt-key add -
echo 'deb https://hub.unity3d.com/linux/repos/deb stable main' > /etc/apt/sources.list.d/unityhub.list
apt update
apt install -y unityhub

# 安装 Unity 版本
echo "Installing Unity versions..."
sudo -u jenkins unityhub --headless install --version 2021.3.10f1 --changeset fb119bb0b476
sudo -u jenkins unityhub --headless install --version 2022.3.10f1 --changeset ff3792e53c62
sudo -u jenkins unityhub --headless install --version 2023.1.5f1 --changeset 9dce81d9e7e0

# 安装 Unity 模块
echo "Installing Unity modules..."
sudo -u jenkins unityhub --headless install-modules --version 2022.3.10f1 --module android
sudo -u jenkins unityhub --headless install-modules --version 2022.3.10f1 --module ios
sudo -u jenkins unityhub --headless install-modules --version 2022.3.10f1 --module webgl

# 安装 Android SDK
echo "Installing Android SDK..."
mkdir -p /opt/android-sdk
cd /opt/android-sdk
wget https://dl.google.com/android/repository/commandlinetools-linux-8512546_latest.zip
unzip commandlinetools-linux-8512546_latest.zip
chown -R jenkins:jenkins /opt/android-sdk

# 设置环境变量
cat >> /home/jenkins/.bashrc << 'EOF'
export JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto
export UNITY_HOME=/opt/unity
export ANDROID_HOME=/opt/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/bin:$ANDROID_HOME/platform-tools
EOF

# 创建 Unity 构建脚本模板
mkdir -p /opt/unity/scripts
cat > /opt/unity/scripts/BuildScript.cs << 'EOF'
using UnityEngine;
using UnityEditor;
using System.Linq;

public class BuildScript
{
    public static void BuildAndroid()
    {
        string[] scenes = EditorBuildSettings.scenes
            .Where(scene => scene.enabled)
            .Select(scene => scene.path)
            .ToArray();
            
        string buildPath = "Builds/Android/game.apk";
        BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.Android, BuildOptions.None);
        
        if (System.IO.File.Exists(buildPath))
        {
            Debug.Log("Android build completed successfully: " + buildPath);
        }
        else
        {
            Debug.LogError("Android build failed!");
            EditorApplication.Exit(1);
        }
    }
    
    public static void BuildiOS()
    {
        string[] scenes = EditorBuildSettings.scenes
            .Where(scene => scene.enabled)
            .Select(scene => scene.path)
            .ToArray();
            
        string buildPath = "Builds/iOS";
        BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.iOS, BuildOptions.None);
        
        Debug.Log("iOS build completed: " + buildPath);
    }
}
EOF

# 设置完成标志
touch /tmp/setup-complete
echo "Unity Build Agent AMI setup completed successfully"
```

### 阶段 4: 构建流水线

#### 4.1 Unity 项目 Jenkinsfile
```groovy
pipeline {
    agent { 
        label 'unity linux build'
    }
    
    environment {
        UNITY_VERSION = '2022.3.10f1'
        BUILD_TARGET = 'Android'
        UNITY_LICENSE = credentials('unity-license')
    }
    
    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/company/unity-project.git'
            }
        }
        
        stage('Unity License') {
            steps {
                script {
                    // 激活 Unity 许可证
                    sh """
                        /opt/unity/${UNITY_VERSION}/Editor/Unity \\
                            -batchmode \\
                            -quit \\
                            -serial ${UNITY_LICENSE_PSW} \\
                            -username ${UNITY_LICENSE_USR} \\
                            -password ${UNITY_LICENSE_PSW}
                    """
                }
            }
        }
        
        stage('Build Android') {
            steps {
                script {
                    sh """
                        /opt/unity/${UNITY_VERSION}/Editor/Unity \\
                            -batchmode \\
                            -quit \\
                            -projectPath \${WORKSPACE} \\
                            -buildTarget Android \\
                            -executeMethod BuildScript.BuildAndroid \\
                            -logFile \${WORKSPACE}/unity-build.log
                    """
                }
            }
        }
        
        stage('Test') {
            steps {
                script {
                    // 运行 Unity 测试
                    sh """
                        /opt/unity/${UNITY_VERSION}/Editor/Unity \\
                            -batchmode \\
                            -quit \\
                            -projectPath \${WORKSPACE} \\
                            -runTests \\
                            -testPlatform PlayMode \\
                            -testResults \${WORKSPACE}/test-results.xml \\
                            -logFile \${WORKSPACE}/unity-test.log
                    """
                }
            }
            post {
                always {
                    publishTestResults testResultsPattern: 'test-results.xml'
                }
            }
        }
        
        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'Builds/**/*.apk', fingerprint: true
                archiveArtifacts artifacts: '*.log', fingerprint: true
            }
        }
    }
    
    post {
        always {
            // 清理工作空间
            cleanWs()
            
            // 返还 Unity 许可证
            sh """
                /opt/unity/${UNITY_VERSION}/Editor/Unity \\
                    -batchmode \\
                    -quit \\
                    -returnlicense
            """
        }
        success {
            echo 'Unity build completed successfully!'
        }
        failure {
            echo 'Unity build failed!'
        }
    }
}
```

## 部署和验证

### 1. 部署脚本
```bash
#!/bin/bash
# deploy-ec2-fleet-solution.sh

set -e

echo "Deploying EC2 Fleet Jenkins solution..."

# 1. 构建 Unity AMI
echo "Building Unity Agent AMI..."
./scripts/build-unity-ami.sh

# 2. 部署 CDK 基础设施
echo "Deploying infrastructure..."
cd jenkins-plugin-cdk
cdk deploy --all --require-approval never

# 3. 配置 Jenkins
echo "Configuring Jenkins..."
./scripts/configure-jenkins.sh

# 4. 验证部署
echo "Verifying deployment..."
./scripts/verify-deployment.sh

echo "Deployment completed successfully!"
```

### 2. 验证脚本
```bash
#!/bin/bash
# verify-deployment.sh

set -e

echo "Verifying EC2 Fleet Jenkins deployment..."

# 检查 Jenkins Master
JENKINS_URL=$(aws ssm get-parameter --name "/jenkins/master/url" --query 'Parameter.Value' --output text)
if curl -s "$JENKINS_URL/login" > /dev/null; then
    echo "✅ Jenkins Master is accessible"
else
    echo "❌ Jenkins Master is not accessible"
    exit 1
fi

# 检查 EC2 Fleet
FLEET_ID=$(aws ssm get-parameter --name "/jenkins/fleet/id" --query 'Parameter.Value' --output text)
FLEET_STATE=$(aws ec2 describe-fleets --fleet-ids $FLEET_ID --query 'Fleets[0].FleetState' --output text)
if [[ "$FLEET_STATE" == "active" ]]; then
    echo "✅ EC2 Fleet is active"
else
    echo "❌ EC2 Fleet is not active: $FLEET_STATE"
    exit 1
fi

# 触发测试构建
echo "Triggering test build..."
BUILD_ID=$(curl -X POST "$JENKINS_URL/job/unity-test-build/build" \
    --user admin:admin123 \
    --header "Jenkins-Crumb: $(curl -s "$JENKINS_URL/crumbIssuer/api/xml?xpath=concat(//crumbRequestField,\":\",//crumb)" --user admin:admin123)" \
    | grep -o 'item/[0-9]*' | cut -d'/' -f2)

echo "Test build triggered: $BUILD_ID"
echo "Monitor at: $JENKINS_URL/job/unity-test-build/$BUILD_ID/"

echo "Verification completed successfully!"
```

这个基于 EC2 Fleet Plugin 的方案将提供：
- **更好的成本控制** (Spot 实例优化)
- **更高的可靠性** (自动故障转移)
- **更强的扩展性** (Fleet 级别管理)
- **零手动操作** (完全自动化)

通过 Agent JAR 的动态下载和连接机制，Master 可以完全控制 Agent 的行为，包括 Unity 构建的所有操作！