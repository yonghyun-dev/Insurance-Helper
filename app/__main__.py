"""app.__main__

파일 경로: app/__main__.py
목적: `python -m app` 형태의 진입점.
주요 기능: CLI 앱을 호출.
"""

from app.interfaces.cli.app import app

if __name__ == "__main__":
    app()
