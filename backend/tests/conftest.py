import os


def pytest_configure(config):
    """Set up environment variables before test collection.

    This runs at pytest startup, before any test module is imported — in
    particular, before `app.main` is imported (which calls `get_settings()`
    at module level to build the FastAPI app and its CORS middleware). Without
    these env vars set here, that import-time `get_settings()` call would
    raise a validation error before any test's `monkeypatch` fixture ever got
    a chance to run, since fixtures only apply once a test is executing.

    """
    os.environ["SUPABASE_URL"] = "https://example.supabase.co"
    os.environ["SUPABASE_SERVICE_KEY"] = "test-service-key"
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"
