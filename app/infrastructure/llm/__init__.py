"""app.infrastructure.llm

Sprint 16 1a — 추론 LLM provider 중앙화.

흩어진 OpenAI 클라이언트 생성 지점을 한 곳(`client.py`)으로 모은다.
제품 추론은 Upstage Solar 전용이며 OpenAI 폴백이 없다.
"""
