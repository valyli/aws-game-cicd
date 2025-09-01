#!/bin/bash
echo "监控Unity安装进度..."
while true; do
    # 检查Unity是否安装完成
    RESULT=$(aws ssm send-command         --instance-ids i-0e40d5b6ffcfdf68c         --document-name "AWS-RunShellScript"         --parameters 'commands=["test -f /opt/unity/Editor/Unity && echo INSTALLED || echo INSTALLING"]'         --query 'Command.CommandId'         --output text 2>/dev/null)
    
    if [ ! -z "$RESULT" ]; then
        sleep 5
        STATUS=$(aws ssm get-command-invocation             --command-id $RESULT             --instance-id i-0e40d5b6ffcfdf68c             --query 'StandardOutputContent'             --output text 2>/dev/null | tr -d '\n')
        
        echo "$(date): Unity安装状态: $STATUS"
        
        if [ "$STATUS" = "INSTALLED" ]; then
            echo "✅ Unity安装完成！"
            break
        fi
    fi
    
    sleep 60
done
