"""
AWS CDK Stack for ibuddy TS-LLM-Interface
Deploys the application on AWS ECS with Fargate
"""

from aws_cdk import (
    Stack,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as sm,
    aws_s3 as s3,
    Duration,
    RemovalPolicy
)
from constructs import Construct

class IbuddyStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC for the application
        vpc = ec2.Vpc(
            self, "IbuddyVPC",
            max_azs=2,
            nat_gateways=1
        )

        # S3 bucket for storing generated files (alternative to local storage)
        reports_bucket = s3.Bucket(
            self, "IbuddyReportsBucket",
            bucket_name=f"ibuddy-reports-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(90)  # Auto-delete old reports after 90 days
                )
            ]
        )

        # ECS Cluster
        cluster = ecs.Cluster(
            self, "IbuddyCluster",
            vpc=vpc,
            cluster_name="ibuddy-cluster"
        )

        # Task Role with necessary permissions
        task_role = iam.Role(
            self, "IbuddyTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "S3Access": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "s3:PutObject",
                                "s3:GetObject",
                                "s3:ListBucket"
                            ],
                            resources=[
                                reports_bucket.bucket_arn,
                                f"{reports_bucket.bucket_arn}/*"
                            ]
                        )
                    ]
                )
            }
        )

        # Secrets Manager for sensitive environment variables
        secrets = sm.Secret(
            self, "IbuddySecrets",
            description="Secrets for ibuddy application",
            secret_object_value={
                "INTERCOM_PROD_KEY": sm.SecretValue.unsafe_plain_text("REPLACE_ME"),
                "GOOGLE_CREDENTIALS_JSON": sm.SecretValue.unsafe_plain_text("REPLACE_ME"),
                "GDRIVE_FOLDER_ID": sm.SecretValue.unsafe_plain_text("REPLACE_ME"),
                "SLACK_BOT_TOKEN": sm.SecretValue.unsafe_plain_text("REPLACE_ME")
            }
        )

        # Fargate Service with Application Load Balancer
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "IbuddyService",
            cluster=cluster,
            cpu=1024,  # 1 vCPU
            memory_limit_mib=2048,  # 2 GB RAM
            desired_count=2,  # Run 2 instances for high availability
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../"),  # Build from Dockerfile in parent directory
                container_port=8000,
                task_role=task_role,
                environment={
                    "AWS_REGION": self.region,
                    "REPORTS_BUCKET": reports_bucket.bucket_name,
                    "STORAGE_MODE": "s3"  # Use S3 instead of local storage in production
                },
                secrets={
                    "INTERCOM_PROD_KEY": ecs.Secret.from_secrets_manager(secrets, "INTERCOM_PROD_KEY"),
                    "GOOGLE_CREDENTIALS_JSON": ecs.Secret.from_secrets_manager(secrets, "GOOGLE_CREDENTIALS_JSON"),
                    "GDRIVE_FOLDER_ID": ecs.Secret.from_secrets_manager(secrets, "GDRIVE_FOLDER_ID"),
                    "SLACK_BOT_TOKEN": ecs.Secret.from_secrets_manager(secrets, "SLACK_BOT_TOKEN")
                }
            ),
            public_load_balancer=True,
            service_name="ibuddy-service"
        )

        # Configure health check
        fargate_service.target_group.configure_health_check(
            path="/docs",
            healthy_http_codes="200"
        )

        # Auto-scaling configuration
        scaling = fargate_service.service.auto_scale_task_count(
            max_capacity=10,
            min_capacity=2
        )

        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70
        )

        scaling.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=80
        )

        # Output the ALB URL
        self.load_balancer_dns = fargate_service.load_balancer.load_balancer_dns_name 