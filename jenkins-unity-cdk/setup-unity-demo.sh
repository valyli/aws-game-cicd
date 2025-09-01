#!/bin/bash

set -e

echo "🚀 Unity CI/CD Demo Setup Script"
echo "================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Please install AWS CLI first."
        exit 1
    fi
    
    if ! command -v git &> /dev/null; then
        log_error "Git not found. Please install Git first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Deploy Jenkins Agent stack
deploy_agent_stack() {
    log_info "Deploying Jenkins Agent stack..."
    
    if ! source .venv/bin/activate; then
        log_error "Failed to activate virtual environment"
        exit 1
    fi
    
    cdk deploy unity-cicd-jenkins-agent-stack --require-approval never
    log_success "Jenkins Agent stack deployed"
}

# Configure Unity license in Parameter Store
configure_unity_license() {
    log_info "Configuring Unity license..."
    
    echo "Please provide your Unity license information:"
    read -p "Unity Username: " UNITY_USERNAME
    read -s -p "Unity Password: " UNITY_PASSWORD
    echo
    read -p "Unity Serial Number: " UNITY_SERIAL
    
    # Store in Parameter Store
    aws ssm put-parameter --name "/jenkins/unity/username" --value "$UNITY_USERNAME" --type "SecureString" --overwrite
    aws ssm put-parameter --name "/jenkins/unity/password" --value "$UNITY_PASSWORD" --type "SecureString" --overwrite
    aws ssm put-parameter --name "/jenkins/unity/serial" --value "$UNITY_SERIAL" --type "SecureString" --overwrite
    
    log_success "Unity license configured in Parameter Store"
}

# Install required Jenkins plugins
install_jenkins_plugins() {
    log_info "Installing required Jenkins plugins..."
    
    # Get Jenkins instance ID
    JENKINS_INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
        --auto-scaling-group-names unity-cicd-jenkins-master-asg \
        --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
        --output text)
    
    if [ "$JENKINS_INSTANCE_ID" = "None" ] || [ -z "$JENKINS_INSTANCE_ID" ]; then
        log_error "Jenkins instance not found"
        exit 1
    fi
    
    # Install plugins via Jenkins CLI
    JENKINS_URL=$(aws cloudformation describe-stacks \
        --stack-name unity-cicd-jenkins-master-stack \
        --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
        --output text)
    
    # Create plugin installation script
    cat > /tmp/install-plugins.groovy << 'EOF'
import jenkins.model.Jenkins
import hudson.model.UpdateSite
import hudson.PluginWrapper

def plugins = [
    'ec2',
    'git',
    'workflow-aggregator',
    'pipeline-stage-view',
    'build-timeout',
    'timestamper',
    'ws-cleanup',
    'ant',
    'gradle'
]

def instance = Jenkins.getInstance()
def updateCenter = instance.getUpdateCenter()

plugins.each { pluginName ->
    if (!instance.getPluginManager().getPlugin(pluginName)) {
        println "Installing plugin: ${pluginName}"
        def plugin = updateCenter.getPlugin(pluginName)
        if (plugin) {
            plugin.deploy(true)
        }
    } else {
        println "Plugin already installed: ${pluginName}"
    }
}

instance.save()
println "Plugin installation completed"
EOF

    # Upload and execute the script
    aws ssm send-command \
        --instance-ids $JENKINS_INSTANCE_ID \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[\"cp /tmp/install-plugins.groovy /var/lib/jenkins/.jenkins/init.groovy.d/\",\"chown jenkins:jenkins /var/lib/jenkins/.jenkins/init.groovy.d/install-plugins.groovy\",\"systemctl restart jenkins || pkill -f jenkins && sleep 10 && nohup sudo -u jenkins java -Djava.awt.headless=true -jar /usr/share/java/jenkins.war --httpPort=8080 > /var/log/jenkins-manual.log 2>&1 &\"]" \
        > /dev/null
    
    log_success "Jenkins plugins installation initiated"
    log_warning "Please wait 2-3 minutes for Jenkins to restart and install plugins"
}

# Create demo Unity project
create_demo_project() {
    log_info "Creating demo Unity project..."
    
    # Create a simple Unity project structure
    mkdir -p demo-unity-project/{Assets/Scripts,Assets/Editor,ProjectSettings}
    
    # Create a simple C# script
    cat > demo-unity-project/Assets/Scripts/HelloWorld.cs << 'EOF'
using UnityEngine;

public class HelloWorld : MonoBehaviour
{
    void Start()
    {
        Debug.Log("Hello from Unity CI/CD Demo!");
    }
}
EOF

    # Create build script
    cat > demo-unity-project/Assets/Editor/BuildScript.cs << 'EOF'
using UnityEngine;
using UnityEditor;
using System.IO;

public class BuildScript
{
    public static void BuildAndroid()
    {
        string[] scenes = { "Assets/Scenes/SampleScene.unity" };
        string buildPath = "Builds/Android/demo.apk";
        
        Directory.CreateDirectory(Path.GetDirectoryName(buildPath));
        
        BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.Android, BuildOptions.None);
        
        if (File.Exists(buildPath))
        {
            Debug.Log("Android build completed successfully!");
        }
        else
        {
            Debug.LogError("Android build failed!");
            EditorApplication.Exit(1);
        }
    }
    
    public static void BuildWindows()
    {
        string[] scenes = { "Assets/Scenes/SampleScene.unity" };
        string buildPath = "Builds/Windows/demo.exe";
        
        Directory.CreateDirectory(Path.GetDirectoryName(buildPath));
        
        BuildPipeline.BuildPlayer(scenes, buildPath, BuildTarget.StandaloneWindows64, BuildOptions.None);
        
        if (File.Exists(buildPath))
        {
            Debug.Log("Windows build completed successfully!");
        }
        else
        {
            Debug.LogError("Windows build failed!");
            EditorApplication.Exit(1);
        }
    }
}
EOF

    # Create Jenkinsfile
    cat > demo-unity-project/Jenkinsfile << 'EOF'
pipeline {
    agent { label 'unity-linux' }
    
    environment {
        UNITY_PATH = '/opt/unity/Editor/Unity'
        PROJECT_PATH = "${WORKSPACE}"
    }
    
    stages {
        stage('Checkout') {
            steps {
                echo 'Code already checked out by Jenkins'
                sh 'ls -la'
            }
        }
        
        stage('Unity License') {
            steps {
                script {
                    // Activate Unity license
                    sh '''
                        ${UNITY_PATH} -batchmode -quit \
                            -username $(aws ssm get-parameter --name "/jenkins/unity/username" --with-decryption --query 'Parameter.Value' --output text) \
                            -password $(aws ssm get-parameter --name "/jenkins/unity/password" --with-decryption --query 'Parameter.Value' --output text) \
                            -serial $(aws ssm get-parameter --name "/jenkins/unity/serial" --with-decryption --query 'Parameter.Value' --output text) \
                            -logFile /tmp/unity-license.log || true
                    '''
                }
            }
        }
        
        stage('Build Android') {
            steps {
                sh '''
                    ${UNITY_PATH} -batchmode -quit \
                        -projectPath "${PROJECT_PATH}" \
                        -buildTarget Android \
                        -executeMethod BuildScript.BuildAndroid \
                        -logFile /tmp/unity-android-build.log
                '''
                
                archiveArtifacts artifacts: 'Builds/Android/*.apk', fingerprint: true
            }
        }
        
        stage('Build Windows') {
            steps {
                sh '''
                    ${UNITY_PATH} -batchmode -quit \
                        -projectPath "${PROJECT_PATH}" \
                        -buildTarget StandaloneWindows64 \
                        -executeMethod BuildScript.BuildWindows \
                        -logFile /tmp/unity-windows-build.log
                '''
                
                archiveArtifacts artifacts: 'Builds/Windows/*.exe', fingerprint: true
            }
        }
    }
    
    post {
        always {
            // Archive Unity logs
            archiveArtifacts artifacts: '/tmp/unity-*.log', allowEmptyArchive: true
            
            // Clean workspace
            cleanWs()
        }
        success {
            echo 'Unity build completed successfully!'
        }
        failure {
            echo 'Unity build failed!'
        }
    }
}
EOF

    # Create basic project settings
    cat > demo-unity-project/ProjectSettings/ProjectVersion.txt << 'EOF'
m_EditorVersion: 2023.3.0f1
m_EditorVersionWithRevision: 2023.3.0f1 (cd33b3c2c0b7)
EOF

    # Initialize git repository
    cd demo-unity-project
    git init
    git add .
    git commit -m "Initial Unity demo project"
    cd ..
    
    log_success "Demo Unity project created in ./demo-unity-project/"
}

# Create Jenkins job
create_jenkins_job() {
    log_info "Creating Jenkins job..."
    
    # Get Jenkins URL
    JENKINS_URL=$(aws cloudformation describe-stacks \
        --stack-name unity-cicd-jenkins-master-stack \
        --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
        --output text)
    
    echo "Please create a Jenkins job manually:"
    echo "1. Go to ${JENKINS_URL}:8080"
    echo "2. Click 'New Item'"
    echo "3. Enter name: 'unity-demo-build'"
    echo "4. Select 'Pipeline' and click OK"
    echo "5. In Pipeline section, select 'Pipeline script from SCM'"
    echo "6. Set SCM to 'Git'"
    echo "7. Set Repository URL to your demo project Git repository"
    echo "8. Save the job"
    
    log_warning "Manual Jenkins job creation required"
}

# Test Unity Agent
test_unity_agent() {
    log_info "Testing Unity Agent connectivity..."
    
    # Check if agent instances are running
    AGENT_INSTANCES=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=*unity-agent*" "Name=instance-state-name,Values=running" \
        --query 'Reservations[*].Instances[*].InstanceId' \
        --output text)
    
    if [ -z "$AGENT_INSTANCES" ]; then
        log_warning "No Unity agent instances currently running"
        log_info "Agents will be launched automatically when Jenkins jobs are triggered"
    else
        log_success "Found running Unity agent instances: $AGENT_INSTANCES"
    fi
    
    # Test Unity installation on agent (if any running)
    if [ ! -z "$AGENT_INSTANCES" ]; then
        for INSTANCE_ID in $AGENT_INSTANCES; do
            log_info "Testing Unity installation on instance $INSTANCE_ID..."
            
            COMMAND_ID=$(aws ssm send-command \
                --instance-ids $INSTANCE_ID \
                --document-name "AWS-RunShellScript" \
                --parameters 'commands=["/opt/unity/Editor/Unity -version || echo Unity not found"]' \
                --query 'Command.CommandId' \
                --output text)
            
            sleep 5
            
            RESULT=$(aws ssm get-command-invocation \
                --command-id $COMMAND_ID \
                --instance-id $INSTANCE_ID \
                --query 'StandardOutputContent' \
                --output text 2>/dev/null || echo "Command failed")
            
            echo "Unity version on $INSTANCE_ID: $RESULT"
        done
    fi
}

# Verify deployment
verify_deployment() {
    log_info "Verifying complete deployment..."
    
    # Check all stacks
    STACKS=("unity-cicd-vpc-stack" "unity-cicd-storage-stack" "unity-cicd-iam-stack" 
            "unity-cicd-lambda-stack" "unity-cicd-jenkins-master-stack" "unity-cicd-jenkins-agent-stack")
    
    for STACK in "${STACKS[@]}"; do
        STATUS=$(aws cloudformation describe-stacks --stack-name $STACK --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")
        if [ "$STATUS" = "CREATE_COMPLETE" ] || [ "$STATUS" = "UPDATE_COMPLETE" ]; then
            log_success "$STACK: $STATUS"
        else
            log_error "$STACK: $STATUS"
        fi
    done
    
    # Get Jenkins URL
    JENKINS_URL=$(aws cloudformation describe-stacks \
        --stack-name unity-cicd-jenkins-master-stack \
        --query 'Stacks[0].Outputs[?OutputKey==`JenkinsURL`].OutputValue' \
        --output text)
    
    echo ""
    echo "🎉 Unity CI/CD Demo Setup Summary"
    echo "================================="
    echo "Jenkins URL: ${JENKINS_URL}:8080"
    echo "Demo Project: ./demo-unity-project/"
    echo ""
    echo "Next Steps:"
    echo "1. Access Jenkins and complete any remaining plugin installations"
    echo "2. Create a Git repository for the demo project"
    echo "3. Create a Jenkins Pipeline job pointing to your Git repository"
    echo "4. Trigger a build to test Unity compilation"
    echo ""
    echo "For detailed instructions, see: ./UNITY_DEMO_GUIDE.md"
}

# Main execution
main() {
    echo "Starting Unity CI/CD Demo Setup..."
    echo ""
    
    check_prerequisites
    
    # Ask user what to do
    echo "What would you like to do?"
    echo "1. Deploy Jenkins Agent stack"
    echo "2. Configure Unity license"
    echo "3. Install Jenkins plugins"
    echo "4. Create demo Unity project"
    echo "5. Test Unity Agent"
    echo "6. Full setup (all of the above)"
    echo "7. Verify deployment"
    
    read -p "Enter your choice (1-7): " CHOICE
    
    case $CHOICE in
        1)
            deploy_agent_stack
            ;;
        2)
            configure_unity_license
            ;;
        3)
            install_jenkins_plugins
            ;;
        4)
            create_demo_project
            ;;
        5)
            test_unity_agent
            ;;
        6)
            deploy_agent_stack
            configure_unity_license
            install_jenkins_plugins
            create_demo_project
            test_unity_agent
            verify_deployment
            ;;
        7)
            verify_deployment
            ;;
        *)
            log_error "Invalid choice"
            exit 1
            ;;
    esac
    
    log_success "Demo setup completed!"
}

# Run main function
main "$@"