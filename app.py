from backend.app.main import app as asgi_app

try:
    from a2wsgi import ASGIMiddleware
    # Wrap with ASGIMiddleware so standard WSGI servers (e.g. default 'gunicorn app:app' on Render) work directly
    app = ASGIMiddleware(asgi_app)
except Exception:
    app = asgi_app

application = app
__all__ = ["app", "application", "asgi_app"]
