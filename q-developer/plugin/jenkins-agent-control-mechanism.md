# Jenkins Master-Agent 控制机制分析

## 核心疑问解答

### 问题：AMI 中不预装 Jenkins Agent，Master 如何控制 Agent 行为？

## Jenkins Master-Agent 通信机制

### 1. 基本工作原理

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Jenkins       │    │   EC2 Instance   │    │   Build         │
│   Master        │    │   (Clean AMI)    │    │   Execution     │
│                 │    │                  │    │                 │
│ 1. 启动实例      │───▶│ 2. 下载 agent.jar │    │ 4. 执行构建命令  │
│ 3. 建立连接      │◀───│ 3. 连接到 Master  │───▶│ 5. 返回结果     │
│ 6. 销毁实例      │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 2. 详细控制流程

#### 阶段 1: 实例启动和连接
```bash
# EC2 实例启动时的 User Data 脚本
#!/bin/bash

# 1. 基础环境准备
yum update -y
yum install -y java-17-amazon-corretto git docker

# 2. 获取 Jenkins Master 信息
JENKINS_URL=$(aws ssm get-parameter --name "/jenkins/master/url" --query 'Parameter.Value' --output text)
JENKINS_SECRET=$(aws ssm get-parameter --name "/jenkins/agent/secret" --query 'Parameter.Value' --output text)

# 3. 下载 Jenkins Agent JAR (关键步骤!)
curl -o agent.jar "${JENKINS_URL}/jnlpJars/agent.jar"

# 4. 启动 Agent 并连接到 Master
java -jar agent.jar \
  -jnlpUrl "${JENKINS_URL}/computer/${INSTANCE_ID}/jenkins-agent.jnlp" \
  -secret "${JENKINS_SECRET}" \
  -workDir "/opt/jenkins"
```

#### 阶段 2: Master 控制 Agent 执行
```groovy
// Jenkinsfile 中的构建步骤
pipeline {
    agent { label 'unity-linux' }  // Master 选择合适的 Agent
    
    stages {
        stage('Build Unity Project') {
            steps {
                // Master 发送这些命令到 Agent 执行
                sh '''
                    echo "开始 Unity 构建..."
                    /opt/unity/Editor/Unity \
                        -batchmode \
                        -quit \
                        -projectPath ${WORKSPACE}/UnityProject \
                        -buildTarget Android \
                        -executeMethod BuildScript.BuildAndroid
                '''
            }
        }
    }
}
```

## 关键技术点分析

### 1. Agent JAR 的作用

**Agent JAR 是关键组件**，它负责：
- 与 Jenkins Master 建立双向通信通道
- 接收 Master 发送的构建命令
- 在本地执行命令并返回结果
- 管理工作目录和文件传输

```java
// Agent JAR 内部工作原理 (简化)
public class JenkinsAgent {
    public void connect(String masterUrl, String secret) {
        // 1. 建立与 Master 的连接
        Channel channel = connectToMaster(masterUrl, secret);
        
        // 2. 监听 Master 发送的命令
        while (connected) {
            Command cmd = channel.receive();
            Result result = executeCommand(cmd);
            channel.send(result);
        }
    }
    
    private Result executeCommand(Command cmd) {
        // 3. 在本地执行 Master 发送的命令
        Process process = Runtime.getRuntime().exec(cmd.getCommandLine());
        return new Result(process.getExitCode(), process.getOutput());
    }
}
```

### 2. AMI 中需要预装的内容

**AMI 不需要预装 Jenkins Agent JAR**，但需要预装：

```bash
# 必需的基础软件
- Java 17 (运行 agent.jar)
- Git (代码拉取)
- Docker (容器化构建)
- AWS CLI (访问 AWS 服务)

# Unity 特定软件
- Unity Hub
- Unity Editor (多版本)
- Android SDK (如需要)
- iOS Build Tools (如需要)

# 构建工具
- Maven, Gradle, npm 等
```

### 3. EC2 Fleet Plugin 工作机制

参考 [ec2-fleet-plugin](https://github.com/jenkinsci/ec2-fleet-plugin)：

```yaml
# Plugin 配置示例
ec2-fleet:
  name: "unity-build-fleet"
  region: "us-east-1"
  fleet-config-id: "fc-1234567890abcdef0"
  
  # 关键：User Data 脚本
  user-data: |
    #!/bin/bash
    # 下载并启动 Jenkins Agent
    JENKINS_URL="http://jenkins-master:8080"
    curl -o agent.jar "${JENKINS_URL}/jnlpJars/agent.jar"
    java -jar agent.jar -jnlpUrl "${JENKINS_URL}/computer/$(hostname)/jenkins-agent.jnlp"
```

## Unity 构建控制实现

### 1. Master 端配置

```groovy
// Jenkins Pipeline 脚本
pipeline {
    agent { 
        label 'unity-linux'  // Master 根据标签选择 Agent
    }
    
    environment {
        UNITY_VERSION = '2022.3.10f1'
        BUILD_TARGET = 'Android'
    }
    
    stages {
        stage('Checkout') {
            steps {
                // Master 指示 Agent 拉取代码
                git branch: 'main', url: 'https://github.com/company/unity-project.git'
            }
        }
        
        stage('Unity Build') {
            steps {
                script {
                    // Master 发送 Unity 构建命令到 Agent
                    def buildResult = sh(
                        script: """
                            /opt/unity/${UNITY_VERSION}/Editor/Unity \\
                                -batchmode \\
                                -quit \\
                                -projectPath \${WORKSPACE} \\
                                -buildTarget ${BUILD_TARGET} \\
                                -executeMethod BuildScript.BuildAndroid \\
                                -logFile \${WORKSPACE}/unity-build.log
                        """,
                        returnStatus: true
                    )
                    
                    if (buildResult != 0) {
                        error("Unity build failed")
                    }
                }
            }
        }
        
        stage('Upload Artifacts') {
            steps {
                // Master 指示 Agent 上传构建产物
                archiveArtifacts artifacts: 'Builds/**/*.apk', fingerprint: true
                publishHTML([
                    allowMissing: false,
                    alwaysLinkToLastBuild: true,
                    keepAll: true,
                    reportDir: 'Builds',
                    reportFiles: 'build-report.html',
                    reportName: 'Unity Build Report'
                ])
            }
        }
    }
    
    post {
        always {
            // Master 指示 Agent 清理工作目录
            cleanWs()
        }
    }
}
```

### 2. Agent 端准备 (AMI 中预装)

```bash
#!/bin/bash
# AMI 构建脚本 - 预装 Unity 环境

# 安装 Unity Hub
wget -qO - https://hub.unity3d.com/linux/keys/public | apt-key add -
echo 'deb https://hub.unity3d.com/linux/repos/deb stable main' > /etc/apt/sources.list.d/unityhub.list
apt update && apt install -y unityhub

# 安装多个 Unity 版本
unityhub --headless install --version 2021.3.10f1
unityhub --headless install --version 2022.3.10f1
unityhub --headless install --version 2023.1.5f1

# 安装 Android 构建支持
unityhub --headless install-modules --version 2022.3.10f1 --module android

# 创建 Unity 构建脚本
cat > /opt/unity/BuildScript.cs << 'EOF'
using UnityEngine;
using UnityEditor;

public class BuildScript
{
    public static void BuildAndroid()
    {
        string[] scenes = EditorBuildSettings.scenes
            .Where(scene => scene.enabled)
            .Select(scene => scene.path)
            .ToArray();
            
        BuildPipeline.BuildPlayer(scenes, "Builds/game.apk", BuildTarget.Android, BuildOptions.None);
    }
}
EOF
```

### 3. 动态 Agent 创建流程

```python
# EC2 Fleet Plugin 配置 (通过 JCasC)
jenkins_config = {
    "clouds": [
        {
            "ec2Fleet": {
                "name": "unity-build-fleet",
                "awsCredentialsId": "",  # 使用 IAM 角色
                "region": "us-east-1",
                "fleet": "fc-1234567890abcdef0",
                "labelString": "unity linux build",
                "idleMinutes": 10,
                "minSize": 0,
                "maxSize": 10,
                "numExecutors": 2,
                "addNodeOnlyIfRunning": True,
                "restrictUsage": False,
                "scaleExecutorsByWeight": True,
                "initOnlineTimeoutSec": 300,
                "initOnlineCheckIntervalSec": 15,
                "cloudStatusIntervalSec": 10,
                "disableTaskResubmit": False,
                "noDelayProvision": False
            }
        }
    ]
}
```

## 完整的控制流程示例

### 1. 构建任务触发
```
开发者推送代码 → Jenkins 检测到变更 → 触发构建任务
```

### 2. Agent 动态创建
```bash
# Jenkins Master 通过 EC2 Fleet Plugin 创建实例
aws ec2 run-instances \
  --image-id ami-unity-build-env \
  --instance-type c5.large \
  --user-data "$(cat user-data-script.sh)"
```

### 3. Agent 自动连接
```bash
# 实例启动后执行的 User Data
#!/bin/bash
JENKINS_URL="http://jenkins-master:8080"
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)

# 下载 Agent JAR
curl -o agent.jar "${JENKINS_URL}/jnlpJars/agent.jar"

# 连接到 Master
java -jar agent.jar \
  -jnlpUrl "${JENKINS_URL}/computer/${INSTANCE_ID}/jenkins-agent.jnlp" \
  -workDir "/opt/jenkins"
```

### 4. Master 控制构建
```groovy
// Master 发送构建命令到 Agent
node('unity-linux') {
    stage('Build') {
        sh '/opt/unity/2022.3.10f1/Editor/Unity -batchmode -quit -projectPath . -executeMethod BuildScript.BuildAndroid'
    }
}
```

### 5. 构建完成清理
```
构建完成 → Agent 上报结果 → Master 销毁实例
```

## 关键要点总结

### ✅ AMI 中需要预装的：
- **运行环境**: Java, Git, Docker
- **构建工具**: Unity, Android SDK, 编译器
- **系统配置**: 用户、权限、目录结构

### ❌ AMI 中不需要预装的：
- **Jenkins Agent JAR**: 动态下载
- **项目代码**: 运行时拉取
- **构建脚本**: 通过 Jenkinsfile 定义

### 🔑 控制机制核心：
1. **Agent JAR** 是 Master-Agent 通信的桥梁
2. **User Data** 脚本负责下载和启动 Agent
3. **Jenkinsfile** 定义具体的构建步骤
4. **Master** 通过 Agent JAR 远程执行命令

这样，Master 就能完全控制 Agent 的行为，包括 Unity 构建、测试、部署等所有操作！

## EC2 Fleet Plugin 工作机制深度解析

### 核心工作原理确认

**连接方式对比**：
- **Linux Agent**: Jenkins Master ↔ SSH ↔ Linux Agent
- **Windows Agent**: Jenkins Master ↔ JNLP ↔ Windows Agent
- **EC2 Fleet Plugin**: 通过这些连接协议来识别和管理Fleet中的实例

### Fleet Plugin 完整工作流程

```
1. Jenkins Job 触发 (label: 'windows unity fleet')
     ↓
2. Fleet Plugin 检测到需求
     ↓
3. 启动 EC2 实例 (使用 Launch Template)
     ↓
4. User Data 脚本执行
     ↓
5. Agent 下载 agent.jar 并连接 Jenkins
     ↓
6. Plugin 通过标签识别为 Fleet 成员
     ↓
7. 执行构建任务
     ↓
8. 空闲超时后自动终止实例
```

### 关键技术要点

#### 1. 标签匹配机制
```powershell
# Fleet 专用脚本中的关键配置
$agentLabels = "windows unity fleet auto"

# Jenkins Pipeline 中的使用
pipeline {
    agent {
        label 'windows unity fleet'  // 触发 Fleet 扩容
    }
}
```

#### 2. Fleet vs 手动管理对比

**现有手动方式**：
```
手动启动实例 → Agent连接 → 手动管理生命周期 → 手动终止
```

**Fleet自动方式**：
```
Jenkins需要时 → Fleet自动启动 → Agent连接 → 空闲时自动终止
```

#### 3. 实施步骤总结

**步骤1**: 创建Fleet专用Launch Template
- 使用 `windows-fleet-userdata.ps1` 脚本
- 确保包含正确的Fleet标签配置

**步骤2**: 配置EC2 Fleet Plugin
- Jenkins > 系统管理 > 节点管理 > Configure Clouds
- 添加 "Amazon EC2 Fleet"
- 配置Launch Template和标签匹配

**步骤3**: 测试自动扩缩容
- 创建使用Fleet标签的Pipeline
- 验证实例自动启动和终止

### Windows Fleet 特殊考虑

#### JNLP连接特点
- Windows使用JNLP而非SSH连接
- 需要更长的启动超时时间
- 服务化运行确保连接稳定性

#### Fleet兼容性配置
```xml
<!-- Fleet专用节点配置 -->
<slave>
  <name>fleet-windows-agent-{instanceId}</name>
  <label>windows unity fleet auto</label>
  <launcher class="hudson.slaves.JNLPLauncher">
    <!-- JNLP配置 -->
  </launcher>
</slave>
```

### 核心结论

**EC2 Fleet Plugin的本质**：
- 通过标签匹配自动管理实例生命周期
- 依赖标准的Jenkins Master-Agent连接协议
- 将手动的实例管理自动化

**实施关键**：
- 正确的Launch Template配置
- 一致的标签策略
- 适当的超时和连接参数

**最终效果**：
- Jenkins根据构建需求自动扩缩容
- 开发者无需关心基础设施管理
- 成本优化：按需使用，空闲自动释放