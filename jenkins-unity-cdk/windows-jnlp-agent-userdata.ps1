<powershell>
# Windows Jenkins JNLP Agent Auto-Connect Script
Start-Transcript -Path "C:\jenkins-agent-setup.log" -Append

Write-Host "=== Starting Windows Jenkins Agent Setup ==="
Write-Host "Time: $(Get-Date)"

# Get instance metadata
$instanceId = (Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/instance-id" -TimeoutSec 10)
$privateIp = (Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/local-ipv4" -TimeoutSec 10)
$region = (Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/placement/region" -TimeoutSec 10)

Write-Host "Instance ID: $instanceId"
Write-Host "Private IP: $privateIp"
Write-Host "Region: $region"

# Jenkins Master configuration
$jenkinsMasterIp = "10.0.0.154"
$jenkinsUrl = "http://$jenkinsMasterIp:8080"
$jenkinsUser = "valyli"
$jenkinsToken = "11e60bc68521d47c1f32944d4045590e25"
$agentName = "windows-agent-$instanceId"
$workDir = "C:\jenkins"

Write-Host "Jenkins URL: $jenkinsUrl"
Write-Host "Agent Name: $agentName"

# Create work directory
New-Item -ItemType Directory -Path $workDir -Force
Set-Location $workDir

# Install Java
Write-Host "=== Installing Java ==="
$javaUrl = "https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_windows-x64_bin.zip"
try {
    Invoke-WebRequest -Uri $javaUrl -OutFile "openjdk-17.zip" -TimeoutSec 300
    Expand-Archive -Path "openjdk-17.zip" -DestinationPath "C:\Program Files\Java" -Force
    
    $javaHome = "C:\Program Files\Java\jdk-17.0.2"
    [Environment]::SetEnvironmentVariable("JAVA_HOME", $javaHome, "Machine")
    [Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$javaHome\bin", "Machine")
    $env:JAVA_HOME = $javaHome
    $env:PATH += ";$javaHome\bin"
    
    Write-Host "Java installed successfully at: $javaHome"
} catch {
    Write-Host "ERROR: Java installation failed: $_"
    exit 1
}

# Wait for Jenkins Master to be available
Write-Host "=== Waiting for Jenkins Master ==="
$maxAttempts = 30
$attempt = 0
do {
    $attempt++
    try {
        $response = Invoke-WebRequest -Uri "$jenkinsUrl/login" -TimeoutSec 10 -UseBasicParsing
        if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 403) {
            Write-Host "Jenkins Master is ready"
            break
        }
    } catch {
        Write-Host "Attempt $attempt/$maxAttempts: Jenkins not ready, waiting..."
        Start-Sleep -Seconds 10
    }
} while ($attempt -lt $maxAttempts)

if ($attempt -ge $maxAttempts) {
    Write-Host "ERROR: Jenkins Master not accessible after $maxAttempts attempts"
    exit 1
}

# Download Jenkins Agent JAR
Write-Host "=== Downloading Jenkins Agent JAR ==="
try {
    Invoke-WebRequest -Uri "$jenkinsUrl/jnlpJars/agent.jar" -OutFile "$workDir\agent.jar"
    Write-Host "Agent JAR downloaded successfully"
} catch {
    Write-Host "ERROR: Failed to download agent.jar: $_"
    exit 1
}

# Create Jenkins node via CLI
Write-Host "=== Creating Jenkins Agent Node ==="
try {
    # Download Jenkins CLI
    Invoke-WebRequest -Uri "$jenkinsUrl/jnlpJars/jenkins-cli.jar" -OutFile "jenkins-cli.jar"
    
    # Create node XML config
    $nodeXml = @"
<slave>
  <name>$agentName</name>
  <description>Auto-created Windows Agent</description>
  <remoteFS>$workDir</remoteFS>
  <numExecutors>2</numExecutors>
  <mode>NORMAL</mode>
  <retentionStrategy class="hudson.slaves.RetentionStrategy`$Always"/>
  <launcher class="hudson.slaves.JNLPLauncher">
    <workDirSettings>
      <disabled>false</disabled>
      <workDirPath>$workDir</workDirPath>
      <internalDir>remoting</internalDir>
      <failIfWorkDirIsMissing>false</failIfWorkDirIsMissing>
    </workDirSettings>
  </launcher>
  <label>windows auto</label>
  <nodeProperties/>
</slave>
"@
    
    $nodeXml | Out-File -FilePath "node-config.xml" -Encoding UTF8
    
    # Create node using Jenkins CLI
    $javaPath = "$javaHome\bin\java.exe"
    & $javaPath -jar jenkins-cli.jar -s $jenkinsUrl -auth "$jenkinsUser:$jenkinsToken" create-node $agentName < node-config.xml
    Write-Host "Node created successfully"
    Start-Sleep -Seconds 10
} catch {
    Write-Host "Node creation may have failed (possibly already exists): $_"
}

# Get JNLP secret
Write-Host "=== Getting JNLP Connection Info ==="
$maxRetries = 10
$retry = 0
do {
    $retry++
    try {
        $jnlpUrl = "$jenkinsUrl/computer/$agentName/jenkins-agent.jnlp"
        $credentials = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$jenkinsUser:$jenkinsToken"))
        $headers = @{ Authorization = "Basic $credentials" }
        $jnlpContent = Invoke-WebRequest -Uri $jnlpUrl -Headers $headers -UseBasicParsing
        
        if ($jnlpContent.Content -match 'application-desc.*?<argument>([^<]+)</argument>.*?<argument>([^<]+)</argument>') {
            $secret = $matches[1]
            $nodeName = $matches[2]
            Write-Host "JNLP Secret obtained: $secret"
            Write-Host "Node Name: $nodeName"
            break
        }
    } catch {
        Write-Host "Retry $retry/$maxRetries: Getting JNLP info failed, waiting..."
        Start-Sleep -Seconds 10
    }
} while ($retry -lt $maxRetries)

if (-not $secret) {
    Write-Host "ERROR: Could not obtain JNLP secret"
    exit 1
}

# Create Windows service for persistent connection
Write-Host "=== Creating Jenkins Agent Service ==="
$serviceName = "JenkinsAgent"
$serviceDisplayName = "Jenkins Agent - $agentName"
$serviceDescription = "Jenkins JNLP Agent for Windows"

# Remove existing service if exists
try {
    Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $serviceName
} catch {}

# Create new service
$javaPath = "$javaHome\bin\java.exe"
$serviceCommand = "`"$javaPath`" -jar `"$workDir\agent.jar`" -url $jenkinsUrl -secret $secret -name `"$agentName`" -workDir `"$workDir`""

sc.exe create $serviceName binPath= $serviceCommand DisplayName= $serviceDisplayName start= auto
sc.exe description $serviceName $serviceDescription

# Start service
Write-Host "=== Starting Jenkins Agent Service ==="
Start-Service -Name $serviceName
Set-Service -Name $serviceName -StartupType Automatic

Write-Host "=== Jenkins Agent Setup Completed ==="
Write-Host "Service Name: $serviceName"
Write-Host "Agent Name: $agentName"
Write-Host "Work Directory: $workDir"
Write-Host "Jenkins URL: $jenkinsUrl"

# Verify service status
Start-Sleep -Seconds 10
$serviceStatus = Get-Service -Name $serviceName
Write-Host "Service Status: $($serviceStatus.Status)"

Write-Host "=== Setup Complete ==="
Stop-Transcript
</powershell>