import sys
import os
import json
import boto3
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP

# RAG 관련 import 추가
try:
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    sys.stderr.write("⚠️ RAG 관련 모듈(langchain 등)이 설치되지 않았습니다.\n")


# 로그 함수
def log(msg):
    sys.stderr.write(f"[MCP Worker] {msg}\n")
    sys.stderr.flush()


# 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 모듈 임포트
try:
    from app_mcp import security_tool

    log("✅ security_tool 임포트 성공")
except ImportError:
    security_tool = None

try:
    from tools import compliance_tools

    log("✅ compliance_tools 임포트 성공")
except ImportError:
    compliance_tools = None

# --- MCP 서버 초기화 ---
mcp = FastMCP("GuardDuty_Worker")

# 전역 변수
security_box = None
compliance_box = None
vectorstore = None

# 초기화 로직
try:
    session = boto3.Session(region_name="ap-northeast-2")

    if security_tool:
        security_box = security_tool.SecurityToolbox(session)
        log("✅ SecurityToolbox 준비 완료")

    if compliance_tools:
        base_path = os.path.join(current_dir, "tools", "data")
        compliance_box = compliance_tools.ComplianceTool(
            regulations_path=os.path.join(base_path, "regulations"),
            templates_path=os.path.join(base_path, "templates"),
        )
        log("✅ ComplianceTool 준비 완료")
    # 3. RAG(Vector DB) 초기화 (추가됨)
    chroma_path = os.path.join(current_dir, "chroma_db")
    if os.path.exists(chroma_path):
        log("📚 법률 지식베이스(ChromaDB) 로드 중...")
        # loader.py와 동일한 임베딩 모델 사용 (필수)
        embedding_model = HuggingFaceEmbeddings(model_name="jhgan/ko-sbert-nli")

        vectorstore = Chroma(
            persist_directory=chroma_path, embedding_function=embedding_model
        )
        log("✅ ChromaDB 연결 성공")
    else:
        log("⚠️ chroma_db 폴더를 찾을 수 없습니다. (RAG 기능 비활성화)")

except Exception as e:
    log(f"❌ 초기화 실패: {e}")

# --- 도구 정의 ---


@mcp.tool()
async def collect_security_data(target: str) -> str:
    """IP나 사용자 이름을 받아 위협 정보를 수집합니다."""
    log(f"🔍 수집 요청: {target}")
    if not security_box:
        return "오류: SecurityToolbox 로드 실패"

    try:
        end = datetime.utcnow()
        start = end - timedelta(hours=24)
        result = await security_box.list_resources_accessed_by_ip(target, start, end)
        return f"[결과] {result}"
    except Exception as e:
        return f"에러: {str(e)}"


@mcp.tool()
def check_compliance_regulation(data: str, region: str = "KR") -> str:
    """규정 준수 검토"""
    log(f"🔍 규정 검토 요청: {region}")
    if not compliance_box:
        return "오류: ComplianceTool 로드 실패"

    try:
        if isinstance(data, str):
            data = json.loads(data)
        return json.dumps(
            compliance_box.check_regulatory_requirements(data, {}, None),
            ensure_ascii=False,
        )
    except Exception as e:
        return f"에러: {str(e)}"


# --- RAG 도구 (추가됨) ---
@mcp.tool()
async def search_legal_knowledge(query: str) -> str:
    """
    개인정보보호법, GDPR 등 법률 지식베이스에서 정보를 검색합니다.
    법적인 근거가 필요하거나 규제 관련 질문이 들어오면 이 도구를 사용하세요.
    """
    log(f"📚 법률 검색 요청: {query}")

    if not vectorstore:
        return "오류: 지식베이스(ChromaDB)가 로드되지 않았습니다."

    try:
        # 상위 3개 관련 문서 검색
        docs = vectorstore.similarity_search(query, k=3)

        if not docs:
            return "검색 결과가 없습니다."

        results = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source_name", "Unknown")
            content = doc.page_content
            results.append(f"--- [문서 {i+1}] 출처: {source} ---\n{content}\n")

        return "\n".join(results)

    except Exception as e:
        return f"검색 중 오류 발생: {str(e)}"


# ★ 중요: 여기는 uvicorn이 아니라 mcp.run()이어야 함 (api_server.py가 실행해주기 때문)
if __name__ == "__main__":
    mcp.run()
