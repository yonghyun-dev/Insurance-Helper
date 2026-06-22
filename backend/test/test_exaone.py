import sys
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import require_env, settings


TEST_MESSAGE = "보험금 청구 가능 여부를 간단히 알려줘."


def main() -> None:
    api_key = require_env(settings.lg_api_key, "LG_API_KEY")
    endpoint_id = require_env(settings.lg_endpoint_id, "LG_ENDPOINT_ID")
    chat_url = require_env(settings.lg_chat_completions_url, "LG_CHAT_COMPLETIONS_URL")
    response = httpx.post(
        chat_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": endpoint_id,
            "messages": [
                {
                    "role": "system",
                    "content": "당신은 한국어로 답하는 보험 청구 안내 도우미입니다.",
                },
                {
                    "role": "user",
                    "content": TEST_MESSAGE,
                },
            ],
        },
        timeout=45,
    )
    response.raise_for_status()

    data = response.json()
    print(data["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
