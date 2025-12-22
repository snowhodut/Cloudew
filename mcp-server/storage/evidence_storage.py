import boto3
import json
import uuid
from datetime import datetime
from botocore.exceptions import ClientError


class EvidenceStorage:
    def __init__(self):
        # DynamoDB 리소스 연결 (EC2 권한 사용)
        self.dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-2")
        # 시원님이 만드신 테이블 이름
        self.table_name = "incident-analysis"
        self.table = self.dynamodb.Table(self.table_name)

    def save_analysis(self, finding_id: str, analysis_text: str, tools_used: list):
        """
        분석 결과를 DynamoDB에 저장합니다.
        """
        try:
            item = {
                "id": str(uuid.uuid4()),  # 고유 ID
                "finding_id": finding_id,  # 관련 Finding ID (없으면 'general-chat')
                "timestamp": datetime.utcnow().isoformat(),
                "analysis_result": analysis_text,  # Claude의 최종 답변
                "tools_executed": tools_used,  # 사용된 도구 목록 (증거)
                "analyst": "Claude-MCP-Agent",
            }

            self.table.put_item(Item=item)
            print(
                f"✅ [Evidence] 분석 결과가 DynamoDB({self.table_name})에 저장되었습니다."
            )
            return True

        except ClientError as e:
            print(f"⚠️ [Storage Error] DynamoDB 저장 실패: {e}")
            # 테이블이 없거나 권한이 없어도 서버가 죽지 않게 예외 처리
            return False
