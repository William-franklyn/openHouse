"""Production ASGI entrypoint for hosts (Vercel Services, etc.) that need a
top-level `app` instance rather than the `create_app()` factory tests use.
"""

from app.main import create_app

app = create_app()
