import sys
from pathlib import Path

from openai import OpenAI

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import require_env, settings


TEST_MESSAGE = "Hi, how are you?"


def main() -> None:
    api_key = require_env(settings.upstage_api_key, "UPSTAGE_API_KEY")
    base_url = require_env(settings.upstage_base_url, "UPSTAGE_BASE_URL")
    model = require_env(settings.upstage_model, "UPSTAGE_MODEL")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": TEST_MESSAGE,
            }
        ],
        stream=True,
        temperature=0.8,
        max_tokens=65536,
        reasoning_effort="medium",
    )

    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="", flush=True)

    print()


if __name__ == "__main__":
    main()
