from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
    aws_dynamodb as dynamodb,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct


class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. VPC 생성 (가상 네트워크)
        # EC2가 위치할 네트워크 공간입니다.
        vpc = ec2.Vpc(
            self,
            "SecurityProjectVPC",
            max_azs=2,
            nat_gateways=0,  # 비용 절감을 위해 NAT Gateway 제외 (Public Subnet 사용)
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                )
            ],
        )

        # 2. KMS Key 생성 (BYOK 핵심 ⭐)
        # 사용자 API Key를 암호화할 보안 키입니다.
        self.kms_key = kms.Key(
            self,
            "ProjectAuthKey",
            enable_key_rotation=True,
            alias="alias/guardduty-project-key",
            removal_policy=RemovalPolicy.DESTROY,  # 실습용이므로 삭제 가능하게 설정
        )

        # 3. DynamoDB 생성 (DB)
        # 암호화된 API Key를 저장할 데이터베이스입니다.
        self.user_table = dynamodb.Table(
            self,
            "UserConfigTable",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # 4. 보안 그룹 설정 (방화벽)
        # 8000(FastAPI), 8501(Streamlit), 22(SSH) 포트를 엽니다.
        security_group = ec2.SecurityGroup(
            self,
            "WebServerSG",
            vpc=vpc,
            description="Allow SSH, FastAPI, and Streamlit",
            allow_all_outbound=True,
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "Allow SSH"
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(8000), "Allow FastAPI"
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(8501), "Allow Streamlit"
        )

        # 5. EC2 인스턴스 생성 (서버)
        # 여기에 MCP 서버와 웹 서버가 뜹니다.
        instance = ec2.Instance(
            self,
            "MCPServerInstance",
            instance_type=ec2.InstanceType("t3.small"),  # t3.micro보다 넉넉하게
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            security_group=security_group,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            block_devices=[  # 용량 20GB로 넉넉하게
                ec2.BlockDevice(
                    device_name="/dev/xvda", volume=ec2.BlockDeviceVolume.ebs(20)
                )
            ],
        )

        # 6. 권한 부여 (IAM)
        # EC2가 KMS(암호화)와 DynamoDB(저장)를 쓸 수 있게 허락해줍니다.
        self.kms_key.grant_encrypt_decrypt(instance)
        self.user_table.grant_read_write_data(instance)

        # EC2가 AWS 서비스(GuardDuty 등)를 조회할 수 있게 읽기 권한 부여
        instance.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "guardduty:List*",
                    "guardduty:Get*",
                    "cloudtrail:LookupEvents",
                    "iam:Get*",
                    "iam:List*",
                    "ec2:Describe*",
                ],
                resources=["*"],
            )
        )

        # 7. 출력 (배포 후 터미널에 보여줄 정보)
        CfnOutput(self, "InstancePublicIP", value=instance.instance_public_ip)
        CfnOutput(self, "KmsKeyId", value=self.kms_key.key_id)
        CfnOutput(self, "TableName", value=self.user_table.table_name)
