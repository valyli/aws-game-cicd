# Unity Jenkins Agent Windows AMI 手动创建指南

## 1. 启动 Windows EC2 实例

### 1.1 创建实例
```bash
# 启动 Windows Server 2022 实例
aws ec2 run-instances \
  --image-id ami-0c2b0d3fb02824d92 \
  --instance-type c5.2xlarge \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxxx \
  --subnet-id subnet-xxxxxxxxx \
  --block-device-mappings '[{
    "DeviceName": "/dev/sda1",
    "Ebs": {
      "VolumeSize": 150,
      "VolumeType": "gp3",
      "DeleteOnTermination": true
    }
  }]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=unity-agent-windows-builder}]'
```

### 1.2 连接到实例
使用 RDP 连接到 Windows 实例，获取密码：
```bash
aws ec2 get-password-data --instance-id i-xxxxxxxxx --priv-launch-key your-key.pem
```

## 2. 基础软件安装

### 2.1 安装 Chocolatey (包管理器)
在 PowerShell (管理员) 中运行：
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### 2.2 安装基础工具
```powershell
# 安装必要工具
choco install -y git
choco install -y 7zip
choco install -y awscli
choco install -y jdk17
choco install -y nodejs

# 刷新环境变量
refreshenv
```

## 3. Unity 安装

### 3.1 下载 Unity Hub
```powershell
# 创建下载目录
New-Item -ItemType Directory -Path "C:\UnityInstall" -Force
cd C:\UnityInstall

# 下载 Unity Hub
Invoke-WebRequest -Uri "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup.exe" -OutFile "UnityHubSetup.exe"

# 静默安装 Unity Hub
Start-Process -FilePath "UnityHubSetup.exe" -ArgumentList "/S" -Wait
```

### 3.2 安装 Unity Editor
```powershell
# Unity Hub 路径
$unityHubPath = "${env:ProgramFiles}\Unity Hub\Unity Hub.exe"

# 安装 Unity 2022.3.6f1 (调整版本号)
$unityVersion = "2022.3.6f1"
$unityHash = "b9e6e7e9fa2d"

# 下载 Unity Editor
$unityUrl = "https://download.unity3d.com/download_unity/$unityHash/Windows64EditorInstaller/UnitySetup64-$unityVersion.exe"
Invoke-WebRequest -Uri $unityUrl -OutFile "UnitySetup64.exe"

# 静默安装 Unity Editor
Start-Process -FilePath "UnitySetup64.exe" -ArgumentList "/S" -Wait

# 安装 Android Build Support
$androidUrl = "https://download.unity3d.com/download_unity/$unityHash/TargetSupportInstaller/UnitySetup-Android-Support-for-Editor-$unityVersion.exe"
Invoke-WebRequest -Uri $androidUrl -OutFile "UnitySetup-Android.exe"
Start-Process -FilePath "UnitySetup-Android.exe" -ArgumentList "/S" -Wait

# 安装 Windows Build Support (IL2CPP)
$windowsUrl = "https://download.unity3d.com/download_unity/$unityHash/TargetSupportInstaller/UnitySetup-Windows-IL2CPP-Support-for-Editor-$unityVersion.exe"
Invoke-WebRequest -Uri $windowsUrl -OutFile "UnitySetup-Windows-IL2CPP.exe"
Start-Process -FilePath "UnitySetup-Windows-IL2CPP.exe" -ArgumentList "/S" -Wait
```

### 3.3 验证 Unity 安装
```powershell
# 测试 Unity 命令行
$unityPath = "${env:ProgramFiles}\Unity\Hub\Editor\$unityVersion\Editor\Unity.exe"
& $unityPath -version -batchmode -quit
```

## 4. Visual Studio Build Tools 安装

### 4.1 下载并安装 Build Tools
```powershell
# 下载 Visual Studio Build Tools
Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vs_buildtools.exe" -OutFile "vs_buildtools.exe"

# 安装必要组件
Start-Process -FilePath "vs_buildtools.exe" -ArgumentList "--quiet", "--wait", "--add", "Microsoft.VisualStudio.Workload.MSBuildTools", "--add", "Microsoft.VisualStudio.Workload.VCTools", "--add", "Microsoft.VisualStudio.Component.Windows10SDK.19041" -Wait
```

## 5. Android SDK 配置

### 5.1 下载 Android SDK
```powershell
# 创建 Android SDK 目录
New-Item -ItemType Directory -Path "C:\Android\sdk" -Force
cd C:\Android

# 下载 Command Line Tools
Invoke-WebRequest -Uri "https://dl.google.com/android/repository/commandlinetools-win-9477386_latest.zip" -OutFile "commandlinetools.zip"

# 解压
Expand-Archive -Path "commandlinetools.zip" -DestinationPath "C:\Android\sdk"
Move-Item -Path "C:\Android\sdk\cmdline-tools" -Destination "C:\Android\sdk\cmdline-tools-temp"
New-Item -ItemType Directory -Path "C:\Android\sdk\cmdline-tools\latest" -Force
Move-Item -Path "C:\Android\sdk\cmdline-tools-temp\*" -Destination "C:\Android\sdk\cmdline-tools\latest"
Remove-Item -Path "C:\Android\sdk\cmdline-tools-temp" -Recurse
```

### 5.2 配置环境变量和安装 SDK 组件
```powershell
# 设置环境变量
[Environment]::SetEnvironmentVariable("ANDROID_HOME", "C:\Android\sdk", "Machine")
[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";C:\Android\sdk\cmdline-tools\latest\bin;C:\Android\sdk\platform-tools", "Machine")

# 刷新当前会话的环境变量
$env:ANDROID_HOME = "C:\Android\sdk"
$env:PATH += ";C:\Android\sdk\cmdline-tools\latest\bin;C:\Android\sdk\platform-tools"

# 接受许可证并安装组件
cd "C:\Android\sdk\cmdline-tools\latest\bin"
echo y | .\sdkmanager.bat --licenses
.\sdkmanager.bat "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

## 6. Jenkins Agent 配置

### 6.1 创建 Jenkins 服务用户
```powershell
# 创建 Jenkins 用户 (可选，也可以使用系统账户)
# net user jenkins "YourPassword123!" /add
# net localgroup "Remote Desktop Users" jenkins /add

# 创建 Jenkins 工作目录
New-Item -ItemType Directory -Path "C:\Jenkins" -Force
New-Item -ItemType Directory -Path "C:\Jenkins\workspace" -Force
```

### 6.2 下载 Jenkins Agent
```powershell
# 创建 Jenkins agent 下载脚本
@"
@echo off
cd C:\Jenkins
curl -O http://YOUR-JENKINS-MASTER:8080/jnlpJars/agent.jar
"@ | Out-File -FilePath "C:\Jenkins\download-agent.bat" -Encoding ASCII
```

## 7. 缓存卷管理脚本

### 7.1 创建 PowerShell 缓存管理脚本
```powershell
# 创建缓存卷管理脚本
@"
param(
    [Parameter(Mandatory=`$true)]
    [ValidateSet("allocate", "release")]
    [string]`$Action
)

# 获取实例元数据
`$instanceId = (Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/instance-id")
`$az = (Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/placement/availability-zone")
`$region = (Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/placement/region")

switch (`$Action) {
    "allocate" {
        Write-Host "Allocating cache volume..."
        
        # 调用 Lambda 函数分配卷
        `$payload = @{
            availability_zone = `$az
            project_id = "unity-game"
            instance_id = `$instanceId
        } | ConvertTo-Json
        
        `$response = aws lambda invoke --region `$region --function-name unity-cicd-allocate-cache-volume --payload `$payload C:\temp\volume_response.json
        `$volumeInfo = Get-Content C:\temp\volume_response.json | ConvertFrom-Json
        
        if (`$volumeInfo.volume_id) {
            Write-Host "Allocated volume: `$(`$volumeInfo.volume_id)"
            
            # 等待卷可用
            aws ec2 wait volume-available --region `$region --volume-ids `$volumeInfo.volume_id
            
            # 附加卷
            aws ec2 attach-volume --region `$region --volume-id `$volumeInfo.volume_id --instance-id `$instanceId --device xvdf
            
            # 等待附加完成
            aws ec2 wait volume-in-use --region `$region --volume-ids `$volumeInfo.volume_id
            
            # 等待磁盘出现并格式化/挂载
            Start-Sleep -Seconds 10
            
            # 查找新磁盘并初始化
            `$disk = Get-Disk | Where-Object { `$_.PartitionStyle -eq 'RAW' } | Select-Object -First 1
            if (`$disk) {
                Initialize-Disk -Number `$disk.Number -PartitionStyle MBR
                New-Partition -DiskNumber `$disk.Number -UseMaximumSize -AssignDriveLetter | Format-Volume -FileSystem NTFS -NewFileSystemLabel "UnityCache" -Confirm:`$false
                `$driveLetter = (Get-Partition -DiskNumber `$disk.Number | Where-Object { `$_.DriveLetter }).DriveLetter
                Write-Host "Cache volume mounted as `$driveLetter`:"
                
                # 创建缓存目录
                New-Item -ItemType Directory -Path "`$driveLetter`:\UnityCache" -Force
                New-Item -ItemType Directory -Path "`$driveLetter`:\BuildCache" -Force
            }
        } else {
            Write-Host "Failed to allocate cache volume"
            exit 1
        }
    }
    
    "release" {
        Write-Host "Releasing cache volume..."
        
        # 查找附加的缓存卷
        `$volumes = aws ec2 describe-volumes --region `$region --filters "Name=attachment.instance-id,Values=`$instanceId" "Name=tag:Purpose,Values=Jenkins-Cache" --query "Volumes[0].VolumeId" --output text
        
        if (`$volumes -and `$volumes -ne "None") {
            # 卸载磁盘 (Windows 会自动处理)
            
            # 调用 Lambda 释放卷
            `$payload = @{
                volume_id = `$volumes
                instance_id = `$instanceId
            } | ConvertTo-Json
            
            aws lambda invoke --region `$region --function-name unity-cicd-release-cache-volume --payload `$payload C:\temp\release_response.json
            Write-Host "Cache volume released"
        }
    }
}
"@ | Out-File -FilePath "C:\Jenkins\Manage-CacheVolume.ps1" -Encoding UTF8
```

### 7.2 创建启动脚本
```powershell
# 创建 Jenkins Agent 启动脚本
@"
@echo off
echo Starting Jenkins Agent...

REM 分配缓存卷
powershell -ExecutionPolicy Bypass -File C:\Jenkins\Manage-CacheVolume.ps1 -Action allocate

REM 激活 Unity 许可证
powershell -ExecutionPolicy Bypass -File C:\Jenkins\Activate-UnityLicense.ps1

REM 启动 Jenkins Agent (将由 Jenkins Master 配置)
echo Jenkins Agent startup completed
"@ | Out-File -FilePath "C:\Jenkins\StartAgent.bat" -Encoding ASCII
```

## 8. Unity 许可证激活脚本

### 8.1 创建许可证激活脚本
```powershell
@"
# Unity 许可证激活脚本
try {
    `$unityUsername = aws ssm get-parameter --name "/jenkins/unity/username" --with-decryption --query "Parameter.Value" --output text 2>`$null
    `$unityPassword = aws ssm get-parameter --name "/jenkins/unity/password" --with-decryption --query "Parameter.Value" --output text 2>`$null
    `$unitySerial = aws ssm get-parameter --name "/jenkins/unity/serial" --with-decryption --query "Parameter.Value" --output text 2>`$null
    
    if (`$unityUsername -and `$unityPassword -and `$unitySerial) {
        Write-Host "Activating Unity license..."
        
        `$unityPath = "${env:ProgramFiles}\Unity\Hub\Editor\2022.3.6f1\Editor\Unity.exe"
        & `$unityPath -batchmode -quit -username `$unityUsername -password `$unityPassword -serial `$unitySerial
        
        Write-Host "Unity license activation completed"
    } else {
        Write-Host "Unity license credentials not found in SSM Parameter Store"
        Write-Host "Please configure the following parameters:"
        Write-Host "  /jenkins/unity/username"
        Write-Host "  /jenkins/unity/password"
        Write-Host "  /jenkins/unity/serial"
    }
} catch {
    Write-Host "Error activating Unity license: `$_"
}
"@ | Out-File -FilePath "C:\Jenkins\Activate-UnityLicense.ps1" -Encoding UTF8
```

## 9. 环境变量配置

### 9.1 设置系统环境变量
```powershell
# Unity 路径
[Environment]::SetEnvironmentVariable("UNITY_PATH", "${env:ProgramFiles}\Unity\Hub\Editor\2022.3.6f1\Editor\Unity.exe", "Machine")

# Java 路径
$javaPath = (Get-ChildItem "${env:ProgramFiles}\Eclipse Adoptium" -Directory | Select-Object -First 1).FullName
[Environment]::SetEnvironmentVariable("JAVA_HOME", "$javaPath", "Machine")

# Android SDK
[Environment]::SetEnvironmentVariable("ANDROID_HOME", "C:\Android\sdk", "Machine")

# 更新 PATH
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
$newPath = "$currentPath;${env:ProgramFiles}\Unity\Hub\Editor\2022.3.6f1\Editor;C:\Android\sdk\cmdline-tools\latest\bin;C:\Android\sdk\platform-tools"
[Environment]::SetEnvironmentVariable("PATH", $newPath, "Machine")
```

## 10. 验证安装

### 10.1 测试 Unity
```powershell
# 测试 Unity 版本
$unityPath = "${env:ProgramFiles}\Unity\Hub\Editor\2022.3.6f1\Editor\Unity.exe"
& $unityPath -version -batchmode -quit
```

### 10.2 测试 Android SDK
```powershell
# 测试 Android SDK
cd "C:\Android\sdk\cmdline-tools\latest\bin"
.\sdkmanager.bat --list | Select-Object -First 20
```

### 10.3 测试构建工具
```powershell
# 测试 MSBuild
& "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe" -version
```

## 11. 系统优化

### 11.1 禁用不必要的服务
```powershell
# 禁用 Windows Update (可选)
Set-Service -Name wuauserv -StartupType Disabled

# 禁用 Windows Defender 实时保护 (可选，用于构建性能)
Set-MpPreference -DisableRealtimeMonitoring $true
```

### 11.2 配置电源管理
```powershell
# 设置高性能电源计划
powercfg -setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
```

## 12. 创建 AMI

### 12.1 清理系统
```powershell
# 清理临时文件
Remove-Item -Path "C:\UnityInstall" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\temp\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue

# 清理事件日志
wevtutil cl Application
wevtutil cl System
wevtutil cl Security
```

### 12.2 运行 Sysprep (重要)
```powershell
# 运行 Sysprep 准备 AMI
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown
```

### 12.3 创建 AMI
在实例关闭后，在本地执行：
```bash
INSTANCE_ID="i-xxxxxxxxx"  # 替换为实际实例ID

aws ec2 create-image \
  --instance-id $INSTANCE_ID \
  --name "unity-agent-windows-$(date +%Y%m%d-%H%M%S)" \
  --description "Unity Jenkins Agent Windows AMI with Unity 2022.3.6f1" \
  --tag-specifications 'ResourceType=image,Tags=[{Key=Name,Value=unity-agent-windows},{Key=UnityVersion,Value=2022.3.6f1},{Key=OS,Value=Windows},{Key=Purpose,Value=Jenkins-Agent}]'
```

## 13. Jenkins Master 配置

### 13.1 配置 Windows Agent
在 Jenkins Master 中：
1. 进入 Manage Jenkins → Manage Nodes and Clouds → Configure Clouds
2. 添加 Amazon EC2 Cloud
3. 配置参数：
   - **AMI ID**: Windows AMI ID
   - **Instance Type**: c5.2xlarge 或 m5.2xlarge
   - **Platform**: Windows
   - **Root Command Prefix**: `C:\Jenkins\`
   - **Remote FS Root**: `C:\Jenkins\workspace`
   - **Init Script**:
   ```batch
   C:\Jenkins\StartAgent.bat
   ```

### 13.2 配置 Unity 许可证参数
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

## 14. 测试 Pipeline

### 14.1 创建测试 Job
```groovy
pipeline {
    agent {
        label 'unity-windows-agent'
    }
    
    stages {
        stage('Test Unity') {
            steps {
                bat '''
                    "%UNITY_PATH%" -version -batchmode -quit
                '''
            }
        }
        
        stage('Test Build Tools') {
            steps {
                bat '''
                    "%ProgramFiles(x86)%\\Microsoft Visual Studio\\2022\\BuildTools\\MSBuild\\Current\\Bin\\MSBuild.exe" -version
                '''
            }
        }
        
        stage('Test Cache Volume') {
            steps {
                bat '''
                    dir D:\\ || echo No cache volume mounted
                '''
            }
        }
    }
}
```

## 15. 故障排除

### 15.1 常见问题
- **Unity 许可证问题**: 检查 SSM 参数和网络连接
- **缓存卷问题**: 检查 Lambda 函数权限和磁盘管理
- **构建工具问题**: 验证 Visual Studio Build Tools 安装

### 15.2 日志位置
- Unity 日志: `%USERPROFILE%\AppData\Local\Unity\Editor\Editor.log`
- Jenkins 日志: `C:\Jenkins\logs\`
- Windows 事件日志: Event Viewer

完成后您将拥有一个完整的 Windows Unity Jenkins Agent AMI。