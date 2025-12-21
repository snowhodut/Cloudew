import os
import sys
import asyncio
from contextlib import AsyncExitStack
from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 저장소 모듈 경로 설정 및 임포트
# (현재 파일 위치 기준으로 storage 폴더를 찾습니다)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from storage.evidence_storage import EvidenceStorage
except ImportError:
    # 저장소 파일이 아직 없거나 경로 문제 시 에러 방지용 더미 클래스
    print(
        "⚠️ 경고: storage/evidence_storage.py를 찾을 수 없습니다. 저장 기능이 비활성화됩니다."
    )

    class EvidenceStorage:
        def save_analysis(self, *args, **kwargs):
            pass


class ClaudeMCPClient:
    def __init__(self):
        # 1. 우리가 만든 규정/분석 서버 (Python) 경로
        self.local_server_script = os.path.join(current_dir, "server.py")

        # 2. 증거 저장소 초기화 (DynamoDB 연결)
        self.storage = EvidenceStorage()

    async def chat(self, messages: list, api_key: str, system_prompt: str = "") -> str:
        """
        Claude와 대화하며 필요시 로컬/AWS/GitHub MCP 도구를 실행하고,
        최종 결과를 DynamoDB에 저장합니다.
        """
        client = Anthropic(api_key=api_key)

        # --- [핵심] 3개의 MCP 서버 설정 ---
        server_configs = [
            # (1) Local Python Server (규정 준수 체크용)
            StdioServerParameters(
                command=sys.executable,
                args=[self.local_server_script],
                env=os.environ.copy(),
            ),
            # (2) AWS Official Server (GuardDuty, CloudTrail, IAM 등)
            # Node.js(npx)로 실행하며, EC2의 IAM Role과 Region 설정을 사용합니다.
            StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-aws"],
                env={**os.environ.copy(), "AWS_REGION": "ap-northeast-2"},
            ),
            # (3) GitHub Official Server (플레이북 조회용)
            # .env에 있는 GITHUB_PERSONAL_ACCESS_TOKEN을 자동으로 사용합니다.
            StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-github"],
                env=os.environ.copy(),
            ),
        ]

        # 여러 서버와의 비동기 연결 관리
        async with AsyncExitStack() as stack:
            sessions = []
            tool_to_session_map = {}
            all_claude_tools = []
            used_tools_log = []  # [증거용] 사용한 도구 기록 리스트

            print("\n🔌 [MCP] 통합 서버(Local + AWS + GitHub) 연결 시도 중...")

            # 각 서버에 연결하고 도구 목록 가져오기
            for config in server_configs:
                try:
                    read, write = await stack.enter_async_context(stdio_client(config))
                    session = await stack.enter_async_context(
                        ClientSession(read, write)
                    )
                    await session.initialize()

                    tools_result = await session.list_tools()
                    sessions.append(session)

                    # 도구 이름으로 세션 매핑 (어떤 도구가 어떤 서버에 있는지)
                    for tool in tools_result.tools:
                        tool_to_session_map[tool.name] = session
                        all_claude_tools.append(
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.inputSchema,
                            }
                        )
                except Exception as e:
                    # 특정 서버 연결 실패해도 나머지는 동작하도록 예외 처리
                    cmd_name = (
                        config.args[1] if len(config.args) > 1 else config.command
                    )
                    print(f"⚠️ [Error] 서버 연결 실패 ({cmd_name}): {e}")

            print(f"✅ [MCP] 총 {len(all_claude_tools)}개의 도구가  준비되었습니다.")
