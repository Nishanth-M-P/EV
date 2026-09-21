from backend.app.main import app as asgi_app

# Expose asgi_app for ASGI servers (uvicorn)
app = asgi_app

# Backward/Forward compatibility: if gunicorn runs with default sync WSGI worker:
# We implement a compliant WSGI callable fallback or ASGI handler
class WSGIRunner:
    """WSGI adapter fallback so default 'gunicorn app:app' runs FastAPI without crashing."""
    def __init__(self, asgi):
        self.asgi = asgi

    def __call__(self, environ, start_response):
        # If gunicorn called with WSGI signature: environ, start_response
        import asyncio
        from starlette.types import Receive, Scope, Send
        
        # Simple HTTP adapter for sync worker
        status_set = "200 OK"
        headers_set = []
        body_parts = []

        async def run_asgi():
            nonlocal status_set, headers_set, body_parts
            path = environ.get("PATH_INFO", "/")
            method = environ.get("REQUEST_METHOD", "GET")
            query = environ.get("QUERY_STRING", "")
            
            headers = []
            for k, v in environ.items():
                if k.startswith("HTTP_"):
                    headers.append((k[5:].lower().replace("_", "-").encode("latin-1"), v.encode("latin-1")))
                elif k in ("CONTENT_TYPE", "CONTENT_LENGTH"):
                    headers.append((k.lower().replace("_", "-").encode("latin-1"), v.encode("latin-1")))

            scope = {
                "type": "http",
                "http_version": "1.1",
                "method": method,
                "path": path,
                "raw_path": path.encode("latin-1"),
                "query_string": query.encode("latin-1"),
                "headers": headers,
                "server": (environ.get("SERVER_NAME", "localhost"), int(environ.get("SERVER_PORT", 80))),
            }

            input_stream = environ.get("wsgi.input")
            content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            body = input_stream.read(content_length) if input_stream and content_length > 0 else b""

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            async def send(message):
                nonlocal status_set, headers_set, body_parts
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    status_set = f"{status_code} OK"
                    headers_set = [
                        (k.decode("latin-1"), v.decode("latin-1"))
                        for k, v in message.get("headers", [])
                    ]
                elif message["type"] == "http.response.body":
                    body_parts.append(message.get("body", b""))

            await self.asgi(scope, receive, send)

        loop = asyncio.new_process_bus = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run_asgi())
        finally:
            loop.close()

        start_response(status_set, headers_set)
        return body_parts

# WSGI fallback wrapper
application = WSGIRunner(asgi_app)
