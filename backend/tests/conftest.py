import os
import pytest


def pytest_configure(config):
    """Set up environment variables before test collection."""
    os.environ["SUPABASE_URL"] = "https://example.supabase.co"
    os.environ["SUPABASE_SERVICE_KEY"] = "test-service-key"
    os.environ["SUPABASE_JWT_SECRET"] = "test-jwt-secret"
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"
