#!/bin/bash

set -e

echo "🎮 Unity Agent AMI 构建脚本"
echo "=========================="

# 更新系统
echo "1. 更新系统..."
yum update -y

# 安装基础依赖
echo "2. 安装基础依赖..."
yum install -y java-17-amazon-corretto-devel git wget unzip docker htop --allowerasing

# 配置Docker
systemctl enable docker
systemctl start docker
usermod -a -G docker ec2-user

# 安装AWS CLI v2
echo "3. 安装AWS CLI..."
wget -O awscliv2.zip "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"
unzip awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip

# 安装Unity Hub
echo "4. 安装Unity Hub..."
wget -O /opt/UnityHub.AppImage https://public-cdn.cloud.unity3d.com/hub/prod/UnityHub.AppImage
chmod +x /opt/UnityHub.AppImage

# 安装Unity Editor
echo "5. 安装Unity Editor 2023.2.20f1..."
mkdir -p /opt/unity
cd /opt/unity

# 下载Unity Editor
UNITY_VERSION="2023.2.20f1"
UNITY_CHANGESET="b9e6e7e9fa2d"
UNITY_URL="https://download.unity3d.com/download_unity/${UNITY_CHANGESET}/LinuxEditorInstaller/Unity.tar.xz"

echo "下载Unity从: $UNITY_URL"
wget -O Unity.tar.xz "$UNITY_URL"

# 解压Unity
echo "解压Unity..."
tar -xf Unity.tar.xz
rm Unity.tar.xz

# 创建符号链接
ln -sf /opt/unity/Editor/Unity /usr/local/bin/unity

# 设置权限
chown -R ec2-user:ec2-user /opt/unity
chmod +x /opt/unity/Editor/Unity

# 验证Unity安装
echo "6. 验证Unity安装..."
/opt/unity/Editor/Unity -version > /tmp/unity-version.log 2>&1
cat /tmp/unity-version.log

# 安装Android SDK (用于Android构建)
echo "7. 安装Android SDK..."
mkdir -p /opt/android-sdk
cd /opt/android-sdk
wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip
unzip commandlinetools-linux-9477386_latest.zip
rm commandlinetools-linux-9477386_latest.zip

# 设置Android环境变量
echo 'export ANDROID_HOME=/opt/android-sdk' >> /etc/environment
echo 'export PATH=$PATH:$ANDROID_HOME/cmdline-tools/bin:$ANDROID_HOME/platform-tools' >> /etc/environment

# 安装Jenkins Agent依赖
echo "8. 配置Jenkins Agent..."
mkdir -p /opt/jenkins
chown ec2-user:ec2-user /opt/jenkins

# 创建Unity项目缓存目录
mkdir -p /mnt/unity-cache
chown ec2-user:ec2-user /mnt/unity-cache

# 清理临时文件
echo "9. 清理..."
yum clean all
rm -rf /tmp/*
rm -rf /var/tmp/*

echo "✅ Unity Agent AMI构建完成！"
echo "Unity版本: $(cat /tmp/unity-version.log)"
echo "安装路径: /opt/unity/Editor/Unity"