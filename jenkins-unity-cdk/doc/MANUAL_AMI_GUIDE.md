# Unity Jenkins Agent AMI 手动创建指南

## 1. 启动 EC2 实例

### 1.1 创建实例
```bash
# 启动一个用于构建 AMI 的实例
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type c5.2xlarge \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxxx \
  --subnet-id subnet-xxxxxxxxx \
  --block-device-mappings '[{
    "DeviceName": "/dev/xvda",
    "Ebs": {
      "VolumeSize": 100,
      "VolumeType": "gp3",
      "DeleteOnTermination": true
    }
  }]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=unity-agent-builder}]'
```

### 1.2 连接到实例
```bash
ssh -i your-key.pem ec2-user@<instance-ip>
```

## 2. 系统基础环境配置

### 2.1 更新系统
```bash
sudo yum update -y
```

### 2.2 安装基础依赖
```bash
# 安装开发工具
sudo yum groupinstall -y "Development Tools"

# 安装必要的包
sudo yum install -y \
  wget unzip git \
  xorg-x11-server-Xvfb \
  libXcursor libXrandr libXinerama libXi \
  mesa-libGL gtk3 gtk3-devel \
  java-17-amazon-corretto-devel \
  docker
```

### 2.3 配置 Docker
```bash
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -a -G docker ec2-user
# 重新登录以应用组权限
```

## 3. Unity 环境安装

### 3.1 下载 Unity Editor
```bash
# 创建目录
sudo mkdir -p /opt/unity
cd /tmp

# 下载 Unity 2022.3.6f1 (根据实际需要调整版本)
UNITY_VERSION="2022.3.6f1"
UNITY_HASH="b9e6e7e9fa2d"  # 从 Unity 官网获取对应版本的 hash

wget -q "https://download.unity3d.com/download_unity/${UNITY_HASH}/LinuxEditorInstaller/Unity.tar.xz"
```

### 3.2 安装 Unity
```bash
# 解压
tar -xf Unity.tar.xz

# 移动到目标目录
sudo mv Unity /opt/unity/Editor
sudo chown -R root:root /opt/unity
sudo chmod +x /opt/unity/Editor/Unity
```

### 3.3 测试 Unity 安装
```bash
# 启动虚拟显示
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 &

# 测试 Unity
/opt/unity/Editor/Unity -version -batchmode -quit
```

## 4. Android SDK 安装

### 4.1 下载 Android SDK
```bash
cd /tmp
wget -q "https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip"
unzip -q commandlinetools-linux-9477386_latest.zip

# 安装到系统目录
sudo mkdir -p /opt/android-sdk/cmdline-tools
sudo mv cmdline-tools /opt/android-sdk/cmdline-tools/latest
sudo chown -R root:root /opt/android-sdk
```

### 4.2 配置 Android SDK
```bash
# 设置环境变量
export ANDROID_HOME=/opt/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

# 接受许可证
yes | sudo -E $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses

# 安装必要组件
sudo -E $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager \
  "platform-tools" \
  "platforms;android-34" \
  "build-tools;34.0.0"
```

## 5. Jenkins Agent 配置

### 5.1 创建 Jenkins 用户
```bash
sudo useradd -m -s /bin/bash jenkins
sudo usermod -a -G docker jenkins
```

### 5.2 安装 Jenkins Agent JAR
```bash
# 创建 Jenkins 工作目录
sudo mkdir -p /opt/jenkins
sudo chown jenkins:jenkins /opt/jenkins

# 下载 agent.jar (将在运行时从 Jenkins Master 下载)
sudo -u jenkins mkdir -p /opt/jenkins/bin
```

### 5.3 创建环境配置脚本
```bash
sudo tee /etc/profile.d/unity-build-env.sh > /dev/null <<'EOF'
# Unity build environment
export UNITY_PATH=/opt/unity/Editor/Unity
export ANDROID_HOME=/opt/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools
export JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto
EOF
```

## 6. 缓存卷管理脚本

### 6.1 创建缓存管理脚本
```bash
sudo tee /opt/manage-cache-volume.sh > /dev/null <<'EOF'
#!/bin/bash
# Cache volume management script

ACTION=$1
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)
REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)

case $ACTION in
  'allocate')
    echo 'Allocating cache volume...'
    VOLUME_RESPONSE=$(aws lambda invoke \
        --region $REGION \
        --function-name unity-cicd-allocate-cache-volume \
        --payload '{"availability_zone":"'$AZ'","project_id":"unity-game","instance_id":"'$INSTANCE_ID'"}' \
        --output text \
        /tmp/volume_response.json)
    
    VOLUME_ID=$(cat /tmp/volume_response.json | python3 -c "import sys, json; print(json.load(sys.stdin).get('volume_id', ''))")
    
    if [ ! -z "$VOLUME_ID" ]; then
      echo "Allocated volume: $VOLUME_ID"
      
      # Wait and attach volume
      aws ec2 wait volume-available --region $REGION --volume-ids $VOLUME_ID
      aws ec2 attach-volume --region $REGION --volume-id $VOLUME_ID --instance-id $INSTANCE_ID --device /dev/sdf
      aws ec2 wait volume-in-use --region $REGION --volume-ids $VOLUME_ID
      
      # Mount volume
      sudo mkdir -p /mnt/cache
      if ! sudo blkid /dev/xvdf; then
        sudo mkfs.ext4 /dev/xvdf
      fi
      sudo mount /dev/xvdf /mnt/cache
      sudo chown jenkins:jenkins /mnt/cache
      
      echo "Cache volume mounted successfully"
    else
      echo "Failed to allocate cache volume"
      exit 1
    fi
    ;;
  'release')
    echo 'Releasing cache volume...'
    VOLUME_ID=$(aws ec2 describe-volumes \
        --region $REGION \
        --filters "Name=attachment.instance-id,Values=$INSTANCE_ID" "Name=tag:Purpose,Values=Jenkins-Cache" \
        --query "Volumes[0].VolumeId" \
        --output text)
    
    if [ "$VOLUME_ID" != "None" ] && [ ! -z "$VOLUME_ID" ]; then
      sudo umount /mnt/cache || true
      aws lambda invoke \
          --region $REGION \
          --function-name unity-cicd-release-cache-volume \
          --payload '{"volume_id":"'$VOLUME_ID'","instance_id":"'$INSTANCE_ID'"}' \
          /tmp/release_response.json
      echo "Cache volume released"
    fi
    ;;
  *)
    echo "Usage: $0 {allocate|release}"
    exit 1
    ;;
esac
EOF

sudo chmod +x /opt/manage-cache-volume.sh
```

### 6.2 创建启动脚本
```bash
sudo tee /opt/jenkins-agent-startup.sh > /dev/null <<'EOF'
#!/bin/bash
# Jenkins Agent startup script

# Allocate cache volume
/opt/manage-cache-volume.sh allocate

# Start Jenkins agent (will be configured by Jenkins Master)
# This script will be called by cloud-init or systemd service
EOF

sudo chmod +x /opt/jenkins-agent-startup.sh
```

## 7. Unity 许可证配置脚本

```bash
sudo tee /opt/activate-unity-license.sh > /dev/null <<'EOF'
#!/bin/bash
# Unity license activation script

UNITY_USERNAME=$(aws ssm get-parameter --name '/jenkins/unity/username' --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo '')
UNITY_PASSWORD=$(aws ssm get-parameter --name '/jenkins/unity/password' --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo '')
UNITY_SERIAL=$(aws ssm get-parameter --name '/jenkins/unity/serial' --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo '')

if [ ! -z "$UNITY_USERNAME" ] && [ ! -z "$UNITY_PASSWORD" ] && [ ! -z "$UNITY_SERIAL" ]; then
  echo 'Activating Unity license...'
  export DISPLAY=:99
  Xvfb :99 -screen 0 1024x768x24 &
  sleep 2
  /opt/unity/Editor/Unity -batchmode -quit -username "$UNITY_USERNAME" -password "$UNITY_PASSWORD" -serial "$UNITY_SERIAL"
  echo 'Unity license activation completed'
else
  echo 'Unity license credentials not found in SSM Parameter Store'
  echo 'Please configure the following parameters:'
  echo '  /jenkins/unity/username'
  echo '  /jenkins/unity/password'
  echo '  /jenkins/unity/serial'
fi
EOF

sudo chmod +x /opt/activate-unity-license.sh
```

## 8. 验证安装

### 8.1 测试 Unity
```bash
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 &
/opt/unity/Editor/Unity -version -batchmode -quit
```

### 8.2 测试 Android SDK
```bash
export ANDROID_HOME=/opt/android-sdk
$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --list | head -20
```

### 8.3 测试 Docker
```bash
sudo systemctl status docker
docker --version
```

## 9. 创建 AMI

### 9.1 清理系统
```bash
# 清理临时文件
sudo rm -rf /tmp/*
sudo yum clean all
history -c

# 停止服务
sudo systemctl stop docker
```

### 9.2 创建 AMI
```bash
# 在本地机器上执行
INSTANCE_ID="i-xxxxxxxxx"  # 替换为实际实例ID

aws ec2 create-image \
  --instance-id $INSTANCE_ID \
  --name "unity-agent-$(date +%Y%m%d-%H%M%S)" \
  --description "Unity Jenkins Agent AMI with Unity 2022.3.6f1" \
  --no-reboot \
  --tag-specifications 'ResourceType=image,Tags=[{Key=Name,Value=unity-agent},{Key=UnityVersion,Value=2022.3.6f1},{Key=Purpose,Value=Jenkins-Agent}]'
```

## 10. Jenkins Master 配置

### 10.1 在 Jenkins Master 中添加 Cloud 配置

1. 进入 Jenkins → Manage Jenkins → Manage Nodes and Clouds → Configure Clouds
2. 添加 Amazon EC2 Cloud
3. 配置参数：
   - **AMI ID**: 刚创建的 AMI ID
   - **Instance Type**: m5.large 或 c5.large
   - **Security Groups**: Jenkins Agent 安全组
   - **Subnet**: 私有子网
   - **IAM Instance Profile**: Jenkins Agent IAM 角色
   - **Init Script**:
   ```bash
   #!/bin/bash
   /opt/manage-cache-volume.sh allocate
   /opt/activate-unity-license.sh
   ```

### 10.2 配置 Unity 许可证参数

在 AWS Systems Manager Parameter Store 中创建：
```bash
aws ssm put-parameter \
  --name "/jenkins/unity/username" \
  --value "your-unity-username" \
  --type "SecureString"

aws ssm put-parameter \
  --name "/jenkins/unity/password" \
  --value "your-unity-password" \
  --type "SecureString"

aws ssm put-parameter \
  --name "/jenkins/unity/serial" \
  --value "your-unity-serial" \
  --type "SecureString"
```

## 11. 测试 Jenkins Agent

### 11.1 创建测试 Job
在 Jenkins 中创建一个测试 Pipeline：
```groovy
pipeline {
    agent {
        label 'unity-agent'
    }
    
    stages {
        stage('Test Unity') {
            steps {
                sh '''
                    export DISPLAY=:99
                    Xvfb :99 -screen 0 1024x768x24 &
                    sleep 2
                    /opt/unity/Editor/Unity -version -batchmode -quit
                '''
            }
        }
        
        stage('Test Cache Volume') {
            steps {
                sh '''
                    ls -la /mnt/cache/
                    df -h /mnt/cache/
                '''
            }
        }
    }
}
```

## 12. 故障排除

### 12.1 常见问题
- **Unity 许可证问题**: 检查 SSM 参数是否正确配置
- **缓存卷挂载失败**: 检查 Lambda 函数和 IAM 权限
- **Jenkins Agent 连接失败**: 检查安全组和网络配置

### 12.2 日志查看
```bash
# 查看系统日志
sudo journalctl -u docker
sudo tail -f /var/log/messages

# 查看 Unity 日志
ls -la ~/.config/unity3d/Editor.log
```

完成以上步骤后，您将拥有一个完整配置的 Unity Jenkins Agent AMI，可以在 Auto Scaling Group 中使用。