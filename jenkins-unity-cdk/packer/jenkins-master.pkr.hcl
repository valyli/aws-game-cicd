# Packer template for Jenkins Master AMI
packer {
  required_plugins {
    amazon = {
      version = ">= 1.2.8"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

variable "project_prefix" {
  type        = string
  default     = "unity-cicd"
  description = "Project prefix for resource naming"
}

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region"
}

variable "instance_type" {
  type        = string
  default     = "c5.large"
  description = "Instance type for building AMI"
}

variable "jenkins_version" {
  type        = string
  default     = "2.426.1"
  description = "Jenkins version to install"
}

locals {
  timestamp = regex_replace(timestamp(), "[- TZ:]", "")
}

source "amazon-ebs" "jenkins-master" {
  ami_name      = "${var.project_prefix}-jenkins-master-${local.timestamp}"
  instance_type = var.instance_type
  region        = var.aws_region
  
  source_ami_filter {
    filters = {
      name                = "al2023-ami-*-x86_64"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["amazon"]
  }
  
  ssh_username = "ec2-user"
  
  tags = {
    Name        = "${var.project_prefix}-jenkins-master-${local.timestamp}"
    Project     = var.project_prefix
    Component   = "Jenkins-Master"
    BuildDate   = timestamp()
    ManagedBy   = "Packer"
  }
}

build {
  name = "jenkins-master"
  sources = [
    "source.amazon-ebs.jenkins-master"
  ]

  # Update system
  provisioner "shell" {
    inline = [
      "sudo yum update -y",
      "sudo yum install -y wget curl unzip git"
    ]
  }

  # Install Java 17
  provisioner "shell" {
    inline = [
      "sudo yum install -y java-17-amazon-corretto-devel",
      "java -version"
    ]
  }

  # Install Jenkins
  provisioner "shell" {
    inline = [
      "sudo wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo",
      "sudo rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key",
      "sudo yum install -y jenkins-${var.jenkins_version}",
      "sudo systemctl enable jenkins"
    ]
  }

  # Install AWS CLI v2
  provisioner "shell" {
    inline = [
      "curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip'",
      "unzip awscliv2.zip",
      "sudo ./aws/install",
      "aws --version"
    ]
  }

  # Install Docker
  provisioner "shell" {
    inline = [
      "sudo yum install -y docker",
      "sudo systemctl enable docker",
      "sudo usermod -a -G docker jenkins",
      "sudo usermod -a -G docker ec2-user"
    ]
  }

  # Install EFS utilities
  provisioner "shell" {
    inline = [
      "sudo yum install -y amazon-efs-utils"
    ]
  }

  # Copy Jenkins configuration files
  provisioner "file" {
    source      = "../configs/jenkins.yaml"
    destination = "/tmp/jenkins.yaml"
  }

  provisioner "file" {
    source      = "../configs/plugins.txt"
    destination = "/tmp/plugins.txt"
  }

  # Setup Jenkins configuration
  provisioner "shell" {
    inline = [
      "sudo mkdir -p /var/lib/jenkins",
      "sudo chown jenkins:jenkins /var/lib/jenkins",
      "sudo mkdir -p /var/lib/jenkins/init.groovy.d",
      "sudo cp /tmp/jenkins.yaml /var/lib/jenkins/jenkins.yaml",
      "sudo chown jenkins:jenkins /var/lib/jenkins/jenkins.yaml"
    ]
  }

  # Install Jenkins plugins
  provisioner "shell" {
    inline = [
      "sudo mkdir -p /var/lib/jenkins/plugins",
      "sudo chown jenkins:jenkins /var/lib/jenkins/plugins"
    ]
  }

  # Create Jenkins startup script
  provisioner "shell" {
    inline = [
      "sudo tee /opt/jenkins-startup.sh > /dev/null <<'EOF'",
      "#!/bin/bash",
      "# Jenkins startup script for Unity CI/CD",
      "",
      "# Wait for EFS mount",
      "while [ ! -d /var/lib/jenkins ]; do",
      "  echo 'Waiting for EFS mount...'",
      "  sleep 5",
      "done",
      "",
      "# Ensure correct permissions",
      "chown -R jenkins:jenkins /var/lib/jenkins",
      "",
      "# Start Jenkins",
      "systemctl start jenkins",
      "",
      "# Wait for Jenkins to start",
      "while ! curl -s http://localhost:8080 > /dev/null; do",
      "  echo 'Waiting for Jenkins to start...'",
      "  sleep 10",
      "done",
      "",
      "echo 'Jenkins started successfully'",
      "EOF",
      "",
      "sudo chmod +x /opt/jenkins-startup.sh"
    ]
  }

  # Create basic security configuration
  provisioner "shell" {
    inline = [
      "sudo tee /var/lib/jenkins/init.groovy.d/basic-security.groovy > /dev/null <<'EOF'",
      "#!groovy",
      "import jenkins.model.*",
      "import hudson.security.*",
      "import jenkins.security.s2m.AdminWhitelistRule",
      "",
      "def instance = Jenkins.getInstance()",
      "",
      "// Create admin user",
      "def hudsonRealm = new HudsonPrivateSecurityRealm(false)",
      "hudsonRealm.createAccount('admin', 'admin123')",
      "instance.setSecurityRealm(hudsonRealm)",
      "",
      "// Set authorization strategy",
      "def strategy = new FullControlOnceLoggedInAuthorizationStrategy()",
      "strategy.setAllowAnonymousRead(false)",
      "instance.setAuthorizationStrategy(strategy)",
      "",
      "// Disable remoting",
      "instance.getDescriptor('jenkins.CLI').get().setEnabled(false)",
      "",
      "// Save configuration",
      "instance.save()",
      "EOF",
      "",
      "sudo chown jenkins:jenkins /var/lib/jenkins/init.groovy.d/basic-security.groovy"
    ]
  }

  # Clean up
  provisioner "shell" {
    inline = [
      "sudo yum clean all",
      "sudo rm -rf /tmp/*",
      "sudo rm -rf /var/tmp/*",
      "history -c"
    ]
  }
}