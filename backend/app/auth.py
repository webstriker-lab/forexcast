import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from app.config import get_settings


class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=401, detail=detail)


def _get_signing_key(token: str):
    """Fetch the public key that signed `token` from Supabase's JWKS endpoint.

    Supabase Auth signs tokens with an asymmetric key (ES256/RS256) by
    default; this looks up the right key by the token's `kid` header, rather
    than relying on a static shared secret.
    """
    settings = get_settings()
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    client = PyJWKClient(jwks_url)
    return client.get_signing_key_from_jwt(token).key


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        signing_key = _get_signing_key(token)
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token missing subject claim")
    return user_id
