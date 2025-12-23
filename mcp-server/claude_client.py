import os
import sys
import traceback
from anthropic import Anthropic
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


class ClaudeMCPClient:
    def __init__(self, server_script_path: str):
        self.server_script_path = server_script_path

        self.api_key = os.getenv("CLAUDE_API_KEY")
        if not self.api_key:
            raise ValueError("CLAUDE_API_KEY 환경 변수가 필요합니다.")

        self.anthropic = Anthropic(api_key=self.api_key)

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
        finding_id: str = None
    ):
        python_exe = sys.executable
        server_params = StdioServerParameters(
            command=python_exe,
            args=[self.server_script_path],
            env=os.environ.copy()
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools_list = await session.list_tools()
                    anthropic_tools = [{
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.inputSchema
                    } for t in tools_list.tools]

                    response = self.anthropic.messages.create(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=2000,
                        messages=messages,
                        system=system_prompt or "당신은 클라우드 보안 인시던트 분석 전문가입니다.",
                        tools=anthropic_tools
                    )

                    max_iterations = 10
                    iteration = 0

                    while (
                        response is not None
                        and getattr(response, "stop_reason", None) == "tool_use"
                        and iteration < max_iterations
                    ):
                        iteration += 1
                        print(f"🔄 MCP Tool Loop {iteration}/{max_iterations}", flush=True)

                        messages.append({
                            "role": "assistant",
                            "content": response.content
                        })

                        tool_results = []

                        for block in (response.content or []):
                            if getattr(block, "type", None) == "tool_use":
                                try:
                                    mcp_result = await session.call_tool(
                                        block.name,
                                        block.input or {}
                                    )
                                    tool_text = self._extract_mcp_text(mcp_result)
                                except Exception as e:
                                    print("❌ MCP call_tool 실패:", block.name, str(e), flush=True)
                                    traceback.print_exc()
                                    tool_text = f"MCP Tool Error: {e}"

                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": tool_text
                                })

                        if not tool_results:
                            break

                        messages.append({
                            "role": "user",
                            "content": tool_results
                        })

                        response = self.anthropic.messages.create(
                            model="claude-sonnet-4-5-20250929",
                            max_tokens=2000,
                            messages=messages,
                            tools=anthropic_tools
                        )

                    final_text = ""
                    if response and getattr(response, "content", None):
                        for block in response.content:
                            if getattr(block, "type", None) == "text":
                                final_text += getattr(block, "text", "")

                    return final_text or "응답을 생성할 수 없습니다."

        except Exception as e:
            # ✅ ExceptionGroup 포함 모든 예외를 여기서 처리
            print("💥 MCP ERROR:", flush=True)
            traceback.print_exc()
            return f"[MCP ERROR] {e}"

    async def close(self):
        return
