pipeline {
    agent {
        label 'windows unity'  // 使用Windows节点标签
    }
    
    stages {
        stage('Test Agent Connection') {
            steps {
                echo "=== EC2 Fleet Agent Connection Test ==="
                echo "Node Name: ${env.NODE_NAME}"
                echo "Build Number: ${env.BUILD_NUMBER}"
                echo "Workspace: ${env.WORKSPACE}"
                
                script {
                    // 显示系统信息
                    if (isUnix()) {
                        sh '''
                            echo "=== System Information ==="
                            uname -a
                            whoami
                            pwd
                            df -h
                            free -h
                            java -version
                        '''
                    } else {
                        bat '''
                            echo === System Information ===
                            systeminfo | findstr /B /C:"OS Name" /C:"OS Version"
                            echo User: %USERNAME%
                            echo Current Directory: %CD%
                            dir C:\\ /W
                            java -version
                        '''
                    }
                }
            }
        }
        
        stage('Test EC2 Fleet Plugin') {
            steps {
                echo "=== EC2 Fleet Plugin Test ==="
                script {
                    // 获取实例元数据
                    if (isUnix()) {
                        sh '''
                            echo "=== EC2 Instance Metadata ==="
                            TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -s)
                            echo "Instance ID: $(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id)"
                            echo "Instance Type: $(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-type)"
                            echo "Private IP: $(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/local-ipv4)"
                            echo "AZ: $(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/placement/availability-zone)"
                        '''
                    } else {
                        bat '''
                            echo === EC2 Instance Metadata ===
                            curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" -s > token.txt
                            set /p TOKEN=<token.txt
                            curl -H "X-aws-ec2-metadata-token: %TOKEN%" -s http://169.254.169.254/latest/meta-data/instance-id > instance-id.txt
                            set /p INSTANCE_ID=<instance-id.txt
                            curl -H "X-aws-ec2-metadata-token: %TOKEN%" -s http://169.254.169.254/latest/meta-data/instance-type > instance-type.txt
                            set /p INSTANCE_TYPE=<instance-type.txt
                            echo Instance ID: %INSTANCE_ID%
                            echo Instance Type: %INSTANCE_TYPE%
                        '''
                    }
                }
            }
        }
        
        stage('Test Network Connectivity') {
            steps {
                echo "=== Network Connectivity Test ==="
                script {
                    if (isUnix()) {
                        sh '''
                            echo "=== Network Tests ==="
                            echo "Testing Jenkins Master connectivity..."
                            curl -I http://10.0.0.66:8080/login || echo "Jenkins Master not reachable"
                            
                            echo "Testing internet connectivity..."
                            curl -I https://www.google.com || echo "Internet not reachable"
                            
                            echo "Testing AWS services..."
                            aws sts get-caller-identity || echo "AWS CLI not configured"
                        '''
                    } else {
                        bat '''
                            echo === Network Tests ===
                            echo Testing Jenkins Master connectivity...
                            powershell -Command "try { Invoke-WebRequest -Uri http://10.0.0.66:8080/login -Method Head } catch { Write-Host 'Jenkins Master not reachable' }"
                            
                            echo Testing internet connectivity...
                            ping google.com -n 2
                        '''
                    }
                }
            }
        }
        
        stage('Test File Operations') {
            steps {
                echo "=== File Operations Test ==="
                script {
                    if (isUnix()) {
                        sh '''
                            echo "=== File System Tests ==="
                            echo "Creating test file..."
                            echo "Hello from EC2 Fleet Agent!" > test-file.txt
                            cat test-file.txt
                            ls -la test-file.txt
                            rm test-file.txt
                            echo "File operations successful"
                        '''
                    } else {
                        bat '''
                            echo === File System Tests ===
                            echo Creating test file...
                            echo Hello from EC2 Fleet Agent! > test-file.txt
                            type test-file.txt
                            dir test-file.txt
                            del test-file.txt
                            echo File operations successful
                        '''
                    }
                }
            }
        }
    }
    
    post {
        always {
            echo "=== Test Completed ==="
            echo "Agent: ${env.NODE_NAME}"
            echo "Status: Build completed"
        }
        success {
            echo "✅ EC2 Fleet Agent test PASSED"
        }
        failure {
            echo "❌ EC2 Fleet Agent test FAILED"
        }
    }
}