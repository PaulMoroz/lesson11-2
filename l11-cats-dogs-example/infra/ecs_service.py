import json

import pulumi
import pulumi_aws as aws

# Get the ECR docker image from the ecr_docker module
from infra.ecr_docker import docker_image

# Get configuration and stack info
region = aws.config.region
stack = pulumi.get_stack()
project, env = stack.split(".", maxsplit=1)
prefix = stack.replace(".", "-")

config = pulumi.Config()
cpu_architecture = config.require("cpu_architecture")
docker_tag = config.require("docker_tag")

# Get the default VPC
default_vpc = aws.ec2.get_vpc(default=True)

# Get default VPC subnets
default_subnets = aws.ec2.get_subnets(
    filters=[
        aws.ec2.GetSubnetsFilterArgs(
            name="vpc-id",
            values=[default_vpc.id],
        )
    ]
)

# Get existing ECS cluster
ecs_cluster = aws.ecs.get_cluster(cluster_name="dev-cluster")

# Create CloudWatch Log Group for ECS tasks
log_group = aws.cloudwatch.LogGroup(
    f"{prefix}-ecs-logs",
    name=f"/ecs/{prefix}",
    retention_in_days=7,
)

# Create IAM role for ECS task execution
task_exec_role = aws.iam.Role(
    f"{prefix}-ecs-task-exec-role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
)

# Attach AWS managed policy for ECS task execution
task_exec_policy_attachment = aws.iam.RolePolicyAttachment(
    f"{prefix}-ecs-task-exec-policy",
    role=task_exec_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
)

# Create IAM role for the task itself (for app-level permissions)
task_role = aws.iam.Role(
    f"{prefix}-ecs-task-role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
)

# Security group for ECS tasks - allows direct access from internet
ecs_security_group = aws.ec2.SecurityGroup(
    f"{prefix}-ecs-sg",
    vpc_id=default_vpc.id,
    description="Security group for ECS tasks with public access",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=8080,
            to_port=8080,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow HTTP traffic from anywhere on port 8080",
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound traffic",
        ),
    ],
)

# Create ECS task definition
task_definition = aws.ecs.TaskDefinition(
    f"{prefix}-task-def",
    family=f"{prefix}-app",
    cpu="2048",
    memory="4096",
    network_mode="awsvpc",
    requires_compatibilities=["FARGATE"],
    execution_role_arn=task_exec_role.arn,
    task_role_arn=task_role.arn,
    runtime_platform=aws.ecs.TaskDefinitionRuntimePlatformArgs(
        cpu_architecture=cpu_architecture,
        operating_system_family="LINUX",
    ),
    container_definitions=pulumi.Output.all(
        docker_image.repo_digest, log_group.name
    ).apply(
        lambda args: json.dumps(
            [
                {
                    "name": f"{prefix}-container",
                    "image": args[0],
                    "essential": True,
                    "portMappings": [
                        {
                            "containerPort": 8080,
                            "hostPort": 8080,
                            "protocol": "tcp",
                        }
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": args[1],
                            "awslogs-region": region,
                            "awslogs-stream-prefix": "ecs",
                        },
                    },
                    "healthCheck": {
                        "command": [
                            "CMD-SHELL",
                            "curl -f http://localhost:8080/_stcore/health || exit 1",
                        ],
                        "interval": 30,
                        "timeout": 5,
                        "retries": 3,
                        "startPeriod": 60,
                    },
                }
            ]
        )
    ),
)

# Create ECS service without load balancer
ecs_service = aws.ecs.Service(
    f"{prefix}-service",
    cluster=ecs_cluster.arn,
    task_definition=task_definition.arn,
    desired_count=1,
    launch_type="FARGATE",
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        assign_public_ip=True,
        subnets=default_subnets.ids,
        security_groups=[ecs_security_group.id],
    ),
)


# Export relevant outputs
pulumi.export(f"{prefix}-ecs-service-name", ecs_service.name)
pulumi.export(f"{prefix}-ecs-cluster-name", ecs_cluster.cluster_name)
pulumi.export(f"{prefix}-log-group-name", log_group.name)
pulumi.export(
    f"{prefix}-access-instructions",
    pulumi.Output.concat(
        "Service deployed! To access your app:\n",
        "1. Go to AWS Console > ECS > Clusters > dev-cluster\n",
        "2. Click on Services > ",
        ecs_service.name,
        "\n",
        "3. Click on the Tasks tab and select your running task\n",
        "4. Find the Public IP in the Network section\n",
        "5. Access your app at: http://<public-ip>:8080\n",
        "\nOr use AWS CLI:\n",
        "aws ecs list-tasks --cluster dev-cluster --service-name ",
        ecs_service.name,
        " --query 'taskArns[0]' --output text | xargs -I {} aws ecs describe-tasks --cluster dev-cluster --tasks {} --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text | xargs -I {} aws ec2 describe-network-interfaces --network-interface-ids {} --query 'NetworkInterfaces[0].Association.PublicIp' --output text",
    ),
)
