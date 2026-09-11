import time
from collections.abc import Mapping
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError

from .config import Settings, get_settings
from .memory import current_user_claims

bearer_scheme = HTTPBearer(auto_error=False)


class TokenValidator:
    """Validates Microsoft Entra access tokens for the configured API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks: Mapping[str, Any] | None = None
        self._jwks_expires_at = 0.0

    async def _get_jwks(self) -> Mapping[str, Any]:
        now = time.monotonic()
        if self._jwks is not None and now < self._jwks_expires_at:
            return self._jwks

        jwks_url = (
            "https://login.microsoftonline.com/"
            f"{self._settings.msal_tenant_id}/discovery/v2.0/keys"
        )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(jwks_url)
                response.raise_for_status()
                jwks = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise InvalidTokenError("Unable to retrieve Microsoft Entra signing keys") from error

        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise InvalidTokenError("Microsoft Entra signing keys response was invalid")

        self._jwks = jwks
        self._jwks_expires_at = now + 3600
        return jwks

    async def validate(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise InvalidTokenError("Unsupported token signing algorithm")

            jwks = await self._get_jwks()
            signing_key = next(
                (
                    key
                    for key in jwks["keys"]
                    if isinstance(key, dict) and key.get("kid") == header["kid"]
                ),
                None,
            )
            if signing_key is None:
                raise InvalidTokenError("No matching Microsoft Entra signing key")

            claims = jwt.decode(
                token,
                jwt.PyJWK.from_dict(signing_key).key,
                algorithms=["RS256"],
                issuer=self._settings.token_issuers,
                options={
                    "require": ["exp", "iat", "tid"],
                    "verify_aud": False,
                },
            )
            if claims.get("tid") != self._settings.msal_tenant_id:
                raise InvalidTokenError("Token tenant does not match the configured tenant")

            current_user_claims.set(claims)
            return claims
        except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or unverifiable access token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from error


token_validator = TokenValidator(get_settings())


async def require_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    current_user_claims.set(None)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await token_validator.validate(credentials.credentials)
