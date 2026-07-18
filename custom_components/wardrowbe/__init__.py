"""The Wardrowbe integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DevTokenProvider,
    TokenProvider,
    WardrowbeApiError,
    WardrowbeAuthError,
    WardrowbeClient,
)
from .const import (
    AUTH_MODE_DEV,
    AUTH_MODE_OIDC,
    CONF_AUTH_MODE,
    CONF_AUTHORIZE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_EXTERNAL_ID,
    CONF_HOST,
    CONF_ISSUER_URL,
    CONF_SCOPES,
    CONF_TOKEN_URL,
    CONF_USE_PKCE,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import WardrowbeCoordinator
from .http_views import WardrowbeImageProxyView
from .llm_api import async_register_llm_api
from .oauth2 import OIDCTokenProvider, WardrowbeOAuth2Implementation
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.BUTTON,
    Platform.TODO,
]


@dataclass(slots=True)
class WardrowbeRuntime:
    coordinator: WardrowbeCoordinator
    client: WardrowbeClient


type WardrowbeConfigEntry = ConfigEntry[WardrowbeRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: WardrowbeConfigEntry) -> bool:
    """Set up Wardrowbe from a config entry."""
    session = async_get_clientsession(hass)
    host: str = entry.data[CONF_HOST]
    verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, True)
    auth_mode: str = entry.data[CONF_AUTH_MODE]

    token_provider: TokenProvider
    if auth_mode == AUTH_MODE_OIDC:
        # client_secret may be missing/empty for public clients.
        stored_secret = entry.data.get(CONF_CLIENT_SECRET)
        implementation = WardrowbeOAuth2Implementation(
            hass,
            domain=DOMAIN,
            client_id=entry.data[CONF_CLIENT_ID],
            client_secret=stored_secret if stored_secret else None,
            # Entries created before CONF_USE_PKCE existed have no stored
            # value — fall back to the old client_secret-implies-PKCE rule.
            use_pkce=entry.data.get(CONF_USE_PKCE, not stored_secret),
            authorize_url=entry.data[CONF_AUTHORIZE_URL],
            token_url=entry.data[CONF_TOKEN_URL],
            issuer_url=entry.data[CONF_ISSUER_URL],
            name=entry.title,
            scopes=entry.data.get(CONF_SCOPES) or "openid profile email offline_access",
        )
        token_provider = OIDCTokenProvider(hass, entry, implementation)
    elif auth_mode == AUTH_MODE_DEV:
        token_provider = DevTokenProvider(entry.data[CONF_EXTERNAL_ID])
    else:
        raise ConfigEntryAuthFailed(f"Unknown auth mode: {auth_mode}")

    client = WardrowbeClient(
        session,
        host,
        token_provider,
        verify_ssl=verify_ssl,
        entry_id=entry.entry_id,
    )
    coordinator = WardrowbeCoordinator(hass, entry, client)

    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("_image_view_registered"):
        hass.http.register_view(WardrowbeImageProxyView(hass))
        domain_data["_image_view_registered"] = True

    try:
        await coordinator.async_config_entry_first_refresh()
    except WardrowbeAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except WardrowbeApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = WardrowbeRuntime(coordinator=coordinator, client=client)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)
    async_register_llm_api(hass, entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: WardrowbeConfigEntry) -> bool:
    """Unload a Wardrowbe config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and not _other_entries(hass, entry):
        await async_unregister_services(hass)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: WardrowbeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _other_entries(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return any(
        e.entry_id != entry.entry_id
        for e in hass.config_entries.async_entries(DOMAIN)
    )
