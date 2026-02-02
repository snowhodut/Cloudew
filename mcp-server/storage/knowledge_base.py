import os
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings


class SecurityKnowledgeBase:
    def __init__(self):
        self.persist_directory = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "chroma_db"
        )
        self.embedding_model = OpenAIEmbeddings()
        self.vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_model,
            collection_name="security_knowledge_base",
        )

    def search_law_grounding(self, query: str, k: int = 3):
        """
        [Layer 1] 법적 근거 검색 (Source of Truth)
        규정, 법률 조항 원문을 검색합니다.
        """
        filter_rule = {"layer": "law"}
        return self.vectorstore.similarity_search(query, k=k, filter=filter_rule)

    def search_actionable_guide(self, query: str, task_type: str = None, k: int = 3):
        """
        [Layer 2] 대응 매뉴얼 및 템플릿 검색 (Actionable)
        언론 대응 문구, 신고 템플릿 등을 검색합니다.
        """
        # 기본적으로 Layer 2 전체 검색, task_type이 있으면 더 좁혀서 검색
        filter_rule = {"layer": {"$in": ["guide", "template", "playbook"]}}

        if task_type:
            # 예: task="breach_notification" 인 것만 검색
            filter_rule = {
                "$and": [{"layer": {"$ne": "law"}}, {"task": task_type}]  # 법률 아님
            }

        return self.vectorstore.similarity_search(query, k=k, filter=filter_rule)

    def hybrid_search(self, query: str):
        """
        종합 검색: 법적 근거와 대응 가이드를 모두 가져옵니다.
        """
        laws = self.search_law_grounding(query, k=2)
        guides = self.search_actionable_guide(query, k=2)
        return {"laws": laws, "guides": guides}


# 사용 예시
if __name__ == "__main__":
    kb = SecurityKnowledgeBase()
    # 예: 개인정보 유출 시 법적 의무 검색
    results = kb.search_law_grounding("개인정보 유출 신고 기한")
    for doc in results:
        print(f"[법적근거] {doc.page_content[:100]}...")
