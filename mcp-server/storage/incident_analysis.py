# /storage/incident_analysis.py
"""
Incident Analysis Table
-----------------------

목적
보안 인시던트(Incident) 분석 결과와 상태를 저장하는 DynamoDB 테이블 생성 스크립트.

테이블 역할
- 인시던트 분석 요청 기록
- 분석 상태(analyzing / completed / failed)
- 분석 결과 저장 (summary, affected resources 등)
- 과거 사례 조회 / 감사 로그 용도
→ 따라서 "영구 보관"이 기본 가정이며 TTL 적용하지 않음

설계 포인트
1️) PK = id (UUID 기반 Incident ID)
2️) PAY_PER_REQUEST (요청량 변동 많은 환경에서 안전)
3️) SSE(암호화) + PITR(백업) 필수 — 운영 안정성
4️) 테이블이 이미 있으면 재생성하지 않고 안전하게 통과
"""

import boto3
from botocore.exceptions import ClientError

REGION = "ap-northeast-2"
TABLE_NAME = "incident-analysis"


def create_incident_analysis_table():
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    client = boto3.client("dynamodb", region_name=REGION)

    # =========================
    # 1️) 테이블 존재 여부 확인
    # =========================
    try:
        client.describe_table(TableName=TABLE_NAME)
        print(f"[INFO] 테이블 이미 존재: {TABLE_NAME}")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    # =========================
    # 2️) 테이블 생성
    # =========================
    print(f"[INFO] 테이블 생성 시작: {TABLE_NAME}")

    table = dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {
                "AttributeName": "id",   # Incident 고유 ID
                "KeyType": "HASH"
            }
        ],
        AttributeDefinitions=[
            {
                "AttributeName": "id",
                "AttributeType": "S"
            }
        ],
        BillingMode="PAY_PER_REQUEST",  # 용량 자동 관리 (운영 안정성↑)
        SSESpecification={
            "Enabled": True  # 서버사이드 암호화 (보안 데이터 필수)
        },
    )

    print("[INFO] 테이블 생성 중…")
    table.wait_until_exists()
    print("[SUCCESS] 테이블 생성 완료!")

    # =========================
    # 3️) PITR (Point-In-Time Recovery) 활성화
    #     → 실수 삭제 / 사고 대비 백업
    # =========================
    print("[INFO] PITR 활성화 시도…")
    client.update_continuous_backups(
        TableName=TABLE_NAME,
        PointInTimeRecoverySpecification={
            "PointInTimeRecoveryEnabled": True
        }
    )
    print("[SUCCESS] PITR 활성화 완료!")

    print(f"[READY] incident-analysis 테이블 준비 완료 🚀")


if __name__ == "__main__":
    create_incident_analysis_table()
