"""PKCE and client_secret are independent — a confidential client can use
PKCE too, and its secret must still reach the token endpoint on that branch.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.wardrowbe.oauth2 import WardrowbeOAuth2Implementation

TOKEN_URL = "http://issuer.test/token"


def _impl(
    hass: HomeAssistant, *, client_secret: str | None, use_pkce: bool
) -> WardrowbeOAuth2Implementation:
    return WardrowbeOAuth2Implementation(
        hass,
        domain="wardrowbe_test",
        client_id="my-client",
        client_secret=client_secret,
        use_pkce=use_pkce,
        authorize_url="http://issuer.test/authorize",
        token_url=TOKEN_URL,
        issuer_url="http://issuer.test",
        name="Wardrowbe @ test",
    )


async def test_pkce_confidential_client_still_sends_secret(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(TOKEN_URL, json={"access_token": "tok"})
    impl = _impl(hass, client_secret="shh", use_pkce=True)

    await impl._token_request(
        {
            "grant_type": "authorization_code",
            "code": "abc",
            "code_verifier": "verifier123",
        }
    )

    sent = aioclient_mock.mock_calls[0][2]
    assert sent["client_id"] == "my-client"
    assert sent["client_secret"] == "shh"
    assert sent["code_verifier"] == "verifier123"


async def test_pkce_public_client_omits_secret(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(TOKEN_URL, json={"access_token": "tok"})
    impl = _impl(hass, client_secret=None, use_pkce=True)

    await impl._token_request(
        {
            "grant_type": "authorization_code",
            "code": "abc",
            "code_verifier": "verifier123",
        }
    )

    sent = aioclient_mock.mock_calls[0][2]
    assert "client_secret" not in sent
