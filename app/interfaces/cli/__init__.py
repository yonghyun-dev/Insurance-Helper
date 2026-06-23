"""app.interfaces.cli

파일 경로: app/cli/__init__.py
목적: CLI 진입점 패키지. Typer 앱을 export 한다.
"""

from app.interfaces.cli.app import app

__all__ = ["app"]
