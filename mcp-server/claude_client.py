import os
import sys
import traceback
import asyncio
import httpx
from anthropic import AsyncAnthropic
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


class ClaudeMCPClient:
    def __init__(self, server_script_path: str):
        self.server_script_path = server_script_path

        self.api_key = os.getenv("CLAUDE_API_KEY")
        if not self.api_key:
            raise ValueError("CLAUDE_API_KEY 환경 변수가 필요합니다.")

        # 수정: 타임아웃 상세 설정
        timeout_config = httpx.Timeout(
            connect=10.0,  # 서버 연결시도 시간
            read=120.0,  # 답변 기다리는 시간 (2분)
            write=30.0,  # 데이터 보내는 시간
            pool=60.0,
        )

        # AsyncAnthropic 초기화 시 timeout 적용
        self.anthropic = AsyncAnthropic(api_key=self.api_key, timeout=timeout_config)

    def _extract_mcp_text(self, mcp_result) -> str:
        """MCP tool 결과를 안전하게 문자열로 변환"""
        try:
            if not mcp_result or not getattr(mcp_result, "content", None):
                return ""
            parts = []
            for c in mcp_result.content:
                if hasattr(c, "text") and c.text is not None:
                    parts.append(str(c.text))
                else:
                    parts.append(str(c))
            return "\n".join(parts)
        except Exception as e:
            return f"[MCP_RESULT_PARSE_ERROR] {e}"

    async def chat(
        self,
        messages: list,
        api_key: str = None,
        system_prompt: str = None,
        finding_id: str = None,
    ):
        # API Key 덮어쓰기
        if api_key:
            timeout_config = httpx.Timeout(
                connect=10.0, read=120.0, write=30.0, pool=60.0
            )
            client = AsyncAnthropic(api_key=api_key, timeout=timeout_config)
        else:
            client = self.anthropic

        python_exe = sys.executable
        server_params = StdioServerParameters(
            command=python_exe, args=[self.server_script_path], env=os.environ.copy()
        )

        # 원본 리스트 오염 방지를 위해 복사본 생성
        current_messages = list(messages)

        # System 메시지 분리 및 포맷 정리
        filtered_messages = []
        for msg in current_messages:
            if msg.get("role") == "system":
                continue
            filtered_messages.append(
                {"role": msg.get("role"), "content": msg.get("content")}
            )

        print(
            f"🚀 [MCP Client] Starting session... (Msgs: {len(filtered_messages)})",
            flush=True,
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # 도구 목록 가져오기
                    tools_list = await session.list_tools()
                    anthropic_tools = [
                        {
                            "name": t.name,
                            "description": t.description,
                            "input_schema": t.inputSchema,  # MCP SDK 버전에 따라 t.input_schema 일수도 있음 확인 필요
                        }
                        for t in tools_list.tools
                    ]

                    # 1. 첫 번째 Claude 호출
                    response = await client.messages.create(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=2000,
                        messages=filtered_messages,
                        system=system_prompt
                        or "당신은 클라우드 보안 인시던트 분석 전문가입니다.",
                        tools=anthropic_tools,
                    )

                    max_iterations = 10
                    iteration = 0

                    # 2. 도구 사용 루프 (Tool Use Loop)
                    while (
                        response is not None
                        and response.stop_reason == "tool_use"
                        and iteration < max_iterations
                    ):
                        iteration += 1
                        print(
                            f"🔄 [MCP Loop {iteration}] Tool Use Detected...",
                            flush=True,
                        )

                        # Assistant의 도구 사용 요청을 메시지 내역에 추가
                        # (주의: response.content는 텍스트가 아니라 Block 리스트임)
                        current_messages.append(
                            {"role": "assistant", "content": response.content}
                        )

                        # 다음 요청을 위해 filtered_messages 동기화
                        filtered_messages.append(
                            {"role": "assistant", "content": response.content}
                        )

                        tool_results = []

                        # 요청된 도구들 실행
                        for block in response.content:
                            if block.type == "tool_use":
                                tool_name = block.name
                                tool_input = block.input
                                print(f"🔨 Executing Tool: {tool_name}", flush=True)

                                try:
                                    # 도구 실행
                                    mcp_result = await session.call_tool(
                                        tool_name, tool_input
                                    )
                                    tool_text = self._extract_mcp_text(mcp_result)
                                    print(
                                        f"✅ Tool Done: {tool_name} (Length: {len(tool_text)})",
                                        flush=True,
                                    )
                                except Exception as e:
                                    print(
                                        f"❌ Tool Failed: {tool_name} - {e}", flush=True
                                    )
                                    tool_text = f"Tool Execution Error: {str(e)}"

                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": tool_text,
                                    }
                                )

                        # 도구 결과를 메시지 내역에 추가
                        current_messages.append(
                            {"role": "user", "content": tool_results}
                        )
                        filtered_messages.append(
                            {"role": "user", "content": tool_results}
                        )

                        # Claude에게 결과 전달 후 다시 호출
                        response = await client.messages.create(
                            model="claude-sonnet-4-5-20250929",
                            max_tokens=2000,
                            messages=filtered_messages,
                            tools=anthropic_tools,
                        )

                    # 3. 최종 응답 텍스트 추출
                    final_text = ""
                    if response and response.content:
                        for block in response.content:
                            if block.type == "text":
                                final_text += block.text

                    print(
                        f"🏁 [MCP Client] Finished. Response len: {len(final_text)}",
                        flush=True,
                    )
                    return final_text or "응답이 없습니다."

        except Exception as e:
            print(f"💥 [MCP CRITICAL ERROR] {str(e)}", flush=True)
            traceback.print_exc()
            return f"시스템 에러가 발생했습니다: {str(e)}"

    async def close(self):
        pass
