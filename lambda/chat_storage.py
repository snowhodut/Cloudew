# /lambda/chat_storage.py
"""
ChatStorage
-----------
Slack / Dashboard / MCP 대화 로그를 저장하는 DynamoDB Wrapper.

목표
- 세션 단위로 채팅 히스토리를 관리
- 안정적인 DynamoDB Query 패턴 사용
- TTL(3개월) 적용으로 비용 관리
- GSI를 이용해 사용자 단위 / 인시던트 단위 조회 확장 가능

중요 설계 포인트
1️) PK = session_id / SK = timestamp
   → 같은 세션의 메시지를 시간순 정렬 가능

2️) TTL = 90일
   → DynamoDB TTL 활성화 필요 (Console에서 ttl 필드 등록!)

3️) GSI (예상 설계)
   - user-sessions-index
     PK: user_name
     SK: timestamp
   - incident-sessions-index (추후 추가 가능)
"""

import boto3
import time
import uuid
from typing import List, Dict, Optional
from boto3.dynamodb.conditions import Key


class ChatStorage:
    """
    DynamoDB 기반 채팅 저장/조회 클래스.
    Lambda, FastAPI, Streamlit 어디서든 공통으로 사용 가능하도록 설계.
    """

    def __init__(self):
        # DynamoDB 리전 고정 (운영 안정성)
        self.dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-2")
        self.table = self.dynamodb.Table("chat-history")

    # ===============================
    # 메시지 저장
    # ===============================
    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_name: str,
        incident_id: Optional[str] = None,
        mcp_tools_used: Optional[List[str]] = None,
        report_type: Optional[str] = None,
    ) -> Dict:
        """
        DynamoDB에 채팅 메시지 1건을 저장.

        Args:
            session_id: 채팅 세션 ID (Slack 클릭 시 최초 생성)
            role: "user" | "assistant" | "system"
            content: 메시지 텍스트
            user_name: 사용자 이름 (대시보드 사용자 / Slack 사용자)
            incident_id: 연결된 인시던트 ID (선택)
            mcp_tools_used: MCP 도구 실행 기록 (선택)
            report_type: 생성된 리포트 종류 (선택)

        Returns:
            저장된 DynamoDB Item
        """

        now = int(time.time())

        item = {
            "session_id": session_id,
            "timestamp": now,  # Sort Key
            "message_id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "user_name": user_name,
            # DynamoDB TTL — Console에서 ttl 속성 활성화 필수!
            "ttl": now + (90 * 24 * 3600),
        }

        # Optional Field만 conditionally 추가
        if incident_id:
            item["incident_id"] = incident_id

        if mcp_tools_used:
            item["mcp_tools_used"] = mcp_tools_used

        if report_type:
            item["report_type"] = report_type

        self.table.put_item(Item=item)
        return item

    # ===============================
    # 특정 세션 메시지 전체 조회
    # ===============================
    def get_session_messages(self, session_id: str) -> List[Dict]:
        """
        특정 session_id의 전체 메시지를 시간순(오래된 → 최신)으로 조회.

        DynamoDB Query 특징:
        - Key() 조건 필수 (문자열 비교 불가)
        - ScanIndexForward=True → 오름차순 정렬
        """

        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ScanIndexForward=True,
        )

        return response.get("Items", [])

    # ===============================
    # 특정 사용자의 최근 세션 조회
    # ===============================
    def get_user_sessions(self, user_name: str, limit: int = 20) -> List[Dict]:
        """
        특정 사용자(user_name)의 최근 세션 목록 조회.

        ⚠️ 요구 조건
        - DynamoDB GSI 필요: user-sessions-index
        - 설정:
            PK = user_name
            SK = timestamp

        Args:
            user_name: 사용자 이름
            limit: 반환할 세션 수 (기본 20)

        Returns:
            최신순 세션 리스트
        """

        response = self.table.query(
            IndexName="user-sessions-index",
            KeyConditionExpression=Key("user_name").eq(user_name),
            ScanIndexForward=False,  # 최신순
            Limit=limit,
        )

        return response.get("Items", [])

    # ===============================
    # 세션 존재 여부 확인
    # ===============================
    def session_exists(self, session_id: str) -> bool:
        """
        특정 세션이 존재하는지 가볍게 체크.
        Limit=1 로 비용 최소화.
        """

        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            Limit=1,
        )

        return len(response.get("Items", [])) > 0