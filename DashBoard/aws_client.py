import boto3
import os
from dotenv import load_dotenv

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "ap-northeast-2"),
)

guardduty = session.client("guardduty")
s3 = session.client("s3")
logs = session.client("logs")
cw = session.client("cloudwatch")
lambda_client = session.client("lambda")
