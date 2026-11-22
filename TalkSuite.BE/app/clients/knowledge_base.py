import asyncio
from typing import Any

from app.config import settings


class KnowledgeBaseClient:
    """
    AWS Bedrock Knowledge Base client using RetrieveAndGenerate API.

    Option B approach: Bedrock handles retrieval + generation in one call.
    The KB is queried directly — Bedrock retrieves relevant passages,
    injects them as context, and Claude generates a grounded answer.
    """

    def __init__(self):
        self.knowledge_base_id = settings.bedrock_knowledge_base_id
        self.model_arn = f"arn:aws:bedrock:{settings.aws_region}::foundation-model/{settings.bedrock_model_id}"
        self._mock_mode = False
        self.client = None

        try:
            if self.knowledge_base_id:
                import boto3

                # On ECS, credentials come from the task role automatically.
                self.client = boto3.client(
                    "bedrock-agent-runtime", region_name=settings.aws_region
                )
            else:
                self._mock_mode = True
                print("[TalkSuite] Knowledge Base running in MOCK mode (no KB ID configured)")
        except Exception:
            self._mock_mode = True
            print(f"[TalkSuite] Knowledge Base running in MOCK mode ({e})")

    async def retrieve_and_generate(self, query: str) -> dict[str, Any]:
        """
        Send a query to the Knowledge Base and get a generated answer
        with citations. Bedrock handles retrieval + generation internally.

        Returns:
            {
                "answer": "The generated answer text...",
                "citations": [{"text": "...", "source": "s3://..."}]
            }
        """
        if self._mock_mode or not self.knowledge_base_id:
            return self._mock_response(query)

        try:
            response = await asyncio.to_thread(
                self.client.retrieve_and_generate,
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": self.knowledge_base_id,
                        "modelArn": self.model_arn,
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": 5
                            }
                        },
                    },
                },
            )

            answer = response.get("output", {}).get("text", "")
            citations = []
            for citation in response.get("citations", []):
                for ref in citation.get("retrievedReferences", []):
                    citations.append(
                        {
                            "text": ref.get("content", {}).get("text", ""),
                            "source": ref.get("location", {})
                            .get("s3Location", {})
                            .get("uri", ""),
                        }
                    )

            return {"answer": answer, "citations": citations}

        except Exception as e:
            print(f"[TalkSuite] KB RetrieveAndGenerate failed: {e}")
            return {
                "answer": "I couldn't retrieve documentation at this time. Please try again later.",
                "citations": [],
            }

    async def retrieve(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """
        Retrieve relevant passages only (without generation).
        Useful if you want to pass passages to the main LLM yourself.
        """
        if self._mock_mode or not self.knowledge_base_id:
            return []

        try:
            response = await asyncio.to_thread(
                self.client.retrieve,
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": max_results
                    }
                },
            )

            passages = []
            for result in response.get("retrievalResults", []):
                passages.append(
                    {
                        "text": result["content"]["text"],
                        "score": result.get("score", 0.0),
                        "source": result.get("location", {})
                        .get("s3Location", {})
                        .get("uri", ""),
                    }
                )
            return passages

        except Exception as e:
            print(f"[TalkSuite] KB Retrieve failed: {e}")
            return []

    def _mock_response(self, query: str) -> dict[str, Any]:
        """Mock response for development without AWS KB configured."""
        return {
            "answer": (
                f"[MOCK KB] No Knowledge Base configured. "
                f"In production, this would search your documentation for: \"{query}\" "
                f"and return a grounded answer with citations."
            ),
            "citations": [],
        }
