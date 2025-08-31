# Packer template for Unity Agent AMI
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
  default     = "c5.2xlarge"
  description = "Instance type for building AMI"
}

variable "unity_version" {
  type        = string
  default     = "2023.2.20f1"
  description = "Unity version to install"
}

variable "android_sdk_version" {
  type        = string
  default     = "34"
  description = "Android SDK version"
}

locals {
  timestamp = regex_replace(timestamp(), "[- TZ:]", "")
}

source "amazon-ebs" "unity-agent" {
  ami_name      = "${var.project_prefix}-unity-agent-${local.timestamp}"
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
  
  # Larger root volume for Unity and Android SDK
  launch_block_device_mappings {
    device_name = "/dev/xvda"
    volume_size = 100
    volume_type = "gp3"
    iops        = 3000
    throughput  = 125
    encrypted   = true
    delete_on_termination = true
  }
  
  tags = {
    Name         = "${var.project_prefix}-unity-agent-${local.timestamp}"
    Project      = var.project_prefix
    Component    = "Unity-Agent"
    UnityVersion = var.unity_version
    BuildDate    = timestamp()
    ManagedBy    = "Packer"
  }
}

build {
  name = "unity-agent"
  sources = [
    "source.amazon-ebs.unity-agent"
  ]

  # Update system and install dependencies
  provisioner "shell" {
    inline = [
      "sudo yum update -y",
      "sudo yum install -y wget curl unzip git xorg-x11-server-Xvfb",
      "sudo yum groupinstall -y 'Development Tools'"
    ]
  }

  # Install Java 17
  provisioner "shell" {
    inline = [
      "sudo yum install -y java-17-amazon-corretto-devel",
      "java -version"
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
      "sudo usermod -a -G docker ec2-user"
    ]
  }

  # Install Unity Hub
  provisioner "shell" {
    inline = [
      "wget -qO - https://hub.unity3d.com/linux/keys/public | gpg --dearmor | sudo tee /usr/share/keyrings/Unity_Technologies_ApS.gpg > /dev/null",
      "echo 'deb [signed-by=/usr/share/keyrings/Unity_Technologies_ApS.gpg] https://hub.unity3d.com/linux/repos/deb stable main' | sudo tee /etc/apt/sources.list.d/unityhub.list",
      "sudo yum install -y unityhub || echo 'Unity Hub installation may require manual setup'"
    ]
  }

  # Install Unity Editor (headless)
  provisioner "shell" {
    inline = [
      "# Download Unity Editor",
      "mkdir -p /tmp/unity",
      "cd /tmp/unity",
      "wget -q https://download.unity3d.com/download_unity/$(echo ${var.unity_version} | cut -d'f' -f2)/LinuxEditorInstaller/Unity.tar.xz",
      "tar -xf Unity.tar.xz",
      "sudo mkdir -p /opt/unity",
      "sudo mv Unity /opt/unity/Editor",
      "sudo chown -R root:root /opt/unity",
      "sudo chmod +x /opt/unity/Editor/Unity"
    ]
  }

  # Install Android SDK
  provisioner "shell" {
    inline = [
      "# Install Android SDK",
      "mkdir -p /tmp/android",
      "cd /tmp/android",
      "wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip",
      "unzip -q commandlinetools-linux-9477386_latest.zip",
      "sudo mkdir -p /opt/android-sdk/cmdline-tools",
      "sudo mv cmdline-tools /opt/android-sdk/cmdline-tools/latest",
      "sudo chown -R root:root /opt/android-sdk",
      "",
      "# Set up Android SDK",
      "export ANDROID_HOME=/opt/android-sdk",
      "export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools",
      "",
      "# Accept licenses and install SDK components",
      "yes | sudo -E $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses",
      "sudo -E $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager 'platform-tools' 'platforms;android-${var.android_sdk_version}' 'build-tools;34.0.0'"
    ]
  }

  # Install Node.js for additional build tools
  provisioner "shell" {
    inline = [
      "curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -",
      "sudo yum install -y nodejs",
      "node --version",
      "npm --version"
    ]
  }

  # Create Unity license activation script
  provisioner "shell" {
    inline = [
      "sudo tee /opt/activate-unity-license.sh > /dev/null <<'EOF'",
      "#!/bin/bash",
      "# Unity license activation script",
      "",
      "UNITY_USERNAME=$(aws ssm get-parameter --name '/jenkins/unity/username' --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo '')",
      "UNITY_PASSWORD=$(aws ssm get-parameter --name '/jenkins/unity/password' --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo '')",
      "UNITY_SERIAL=$(aws ssm get-parameter --name '/jenkins/unity/serial' --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo '')",
      "",
      "if [ ! -z '$UNITY_USERNAME' ] && [ ! -z '$UNITY_PASSWORD' ] && [ ! -z '$UNITY_SERIAL' ]; then",
      "  echo 'Activating Unity license...'",
      "  /opt/unity/Editor/Unity -batchmode -quit -username '$UNITY_USERNAME' -password '$UNITY_PASSWORD' -serial '$UNITY_SERIAL'",
      "  echo 'Unity license activation completed'",
      "else",
      "  echo 'Unity license credentials not found in SSM Parameter Store'",
      "  echo 'Please configure the following parameters:'",
      "  echo '  /jenkins/unity/username'",
      "  echo '  /jenkins/unity/password'",
      "  echo '  /jenkins/unity/serial'",
      "fi",
      "EOF",
      "",
      "sudo chmod +x /opt/activate-unity-license.sh"
    ]
  }

  # Create cache volume management script
  provisioner "shell" {
    inline = [
      "sudo tee /opt/manage-cache-volume.sh > /dev/null <<'EOF'",
      "#!/bin/bash",
      "# Cache volume management script",
      "",
      "ACTION=$1",
      "INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)",
      "AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)",
      "REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)",
      "",
      "case $ACTION in",
      "  'allocate')",
      "    echo 'Allocating cache volume...'",
      "    VOLUME_RESPONSE=$(aws lambda invoke \\",
      "        --region $REGION \\",
      "        --function-name unity-cicd-allocate-cache-volume \\",
      "        --payload '{\"availability_zone\":\"'$AZ'\",\"project_id\":\"unity-game\",\"instance_id\":\"'$INSTANCE_ID'\"}' \\",
      "        --output text \\",
      "        /tmp/volume_response.json)",
      "    ",
      "    VOLUME_ID=$(cat /tmp/volume_response.json | python3 -c 'import sys, json; print(json.load(sys.stdin).get(\"volume_id\", \"\"))')",
      "    ",
      "    if [ ! -z '$VOLUME_ID' ]; then",
      "      echo 'Allocated volume: $VOLUME_ID'",
      "      ",
      "      # Wait and attach volume",
      "      aws ec2 wait volume-available --region $REGION --volume-ids $VOLUME_ID",
      "      aws ec2 attach-volume --region $REGION --volume-id $VOLUME_ID --instance-id $INSTANCE_ID --device /dev/sdf",
      "      aws ec2 wait volume-in-use --region $REGION --volume-ids $VOLUME_ID",
      "      ",
      "      # Mount volume",
      "      mkdir -p /mnt/cache",
      "      if ! blkid /dev/xvdf; then",
      "        mkfs.ext4 /dev/xvdf",
      "      fi",
      "      mount /dev/xvdf /mnt/cache",
      "      chown ec2-user:ec2-user /mnt/cache",
      "      ",
      "      echo 'Cache volume mounted successfully'",
      "    else",
      "      echo 'Failed to allocate cache volume'",
      "      exit 1",
      "    fi",
      "    ;;",
      "  'release')",
      "    echo 'Releasing cache volume...'",
      "    VOLUME_ID=$(aws ec2 describe-volumes \\",
      "        --region $REGION \\",
      "        --filters 'Name=attachment.instance-id,Values='$INSTANCE_ID 'Name=tag:Purpose,Values=Jenkins-Cache' \\",
      "        --query 'Volumes[0].VolumeId' \\",
      "        --output text)",
      "    ",
      "    if [ '$VOLUME_ID' != 'None' ] && [ ! -z '$VOLUME_ID' ]; then",
      "      umount /mnt/cache || true",
      "      aws lambda invoke \\",
      "          --region $REGION \\",
      "          --function-name unity-cicd-release-cache-volume \\",
      "          --payload '{\"volume_id\":\"'$VOLUME_ID'\",\"instance_id\":\"'$INSTANCE_ID'\"}' \\",
      "          /tmp/release_response.json",
      "      echo 'Cache volume released'",
      "    fi",
      "    ;;",
      "  *)",
      "    echo 'Usage: $0 {allocate|release}'",
      "    exit 1",
      "    ;;",
      "esac",
      "EOF",
      "",
      "sudo chmod +x /opt/manage-cache-volume.sh"
    ]
  }

  # Create environment setup script
  provisioner "shell" {
    inline = [
      "sudo tee /etc/profile.d/unity-build-env.sh > /dev/null <<'EOF'",
      "# Unity build environment",
      "export UNITY_PATH=/opt/unity/Editor/Unity",
      "export ANDROID_HOME=/opt/android-sdk",
      "export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools",
      "export JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto",
      "EOF"
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