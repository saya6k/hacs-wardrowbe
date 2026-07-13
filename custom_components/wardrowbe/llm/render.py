"""Helpers that turn Wardrowbe payloads into voice-satellite card items.

The voice-satellite card auto-renders any tool result containing
``results: [{image_url, ...}]`` or ``featured_image``. Wardrowbe's outfit
and item endpoints already include real photo URLs, so most tools just
forward them. The wardrobe summary tool has no native imagery, so we
synthesise a small SVG card and emit it as a ``data:`` URL.
"""

from __future__ import annotations

import base64
from typing import Any, Sequence

_FONT = (
    "system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',"
    "'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif"
)
_BG = "#0f172a"
_BG_ALT = "#1e293b"
_FG = "#e2e8f0"
_MUTED = "#94a3b8"
_DEFAULT_ACCENT = "#a855f7"  # purple-500

_IMAGE_FIELDS = (
    "image_url",
    "image",
    "thumbnail_url",
    "thumbnail",
    "preview_url",
    "preview",
    "composite_image_url",
    "composite_url",
    "photo_url",
    "photo",
    "media_url",
)


def _esc(text: str | None) -> str:
    if text is None:
        return ""
    s = str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _trunc(text: str | None, limit: int) -> str:
    if text is None:
        return ""
    s = str(text)
    return s if len(s) <= limit else s[: max(limit - 1, 1)] + "…"


def _to_data_url(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _resolve_url(url: str, host: str) -> str:
    if url.startswith(("http://", "https://", "data:")):
        return url
    # Already routed through the HA image-proxy view; voice-satellite-card
    # renders inside HA's origin and resolves the path natively.
    if url.startswith("/api/wardrowbe/image/"):
        return url
    if not host:
        return url
    if url.startswith("/"):
        return f"{host}{url}"
    return f"{host}/{url}"


def extract_image_url(payload: dict[str, Any], host: str) -> str | None:
    """Return the first usable image URL from a Wardrowbe item/outfit."""
    for key in _IMAGE_FIELDS:
        val = payload.get(key)
        if isinstance(val, str) and val:
            return _resolve_url(val, host)
    return None


def outfit_to_results(
    outfit: dict[str, Any], host: str
) -> list[dict[str, Any]]:
    """Convert one outfit dict to a list of voice-satellite gallery items.

    The outfit's composite image (if any) leads, followed by each item
    photo. Items lacking a photo are skipped silently — better to show
    fewer real cards than to render placeholders.
    """
    results: list[dict[str, Any]] = []
    composite = extract_image_url(outfit, host)
    if composite:
        results.append(
            {
                "image_url": composite,
                "thumbnail_url": composite,
                "title": _outfit_label(outfit),
            }
        )
    for item in outfit.get("items") or []:
        if not isinstance(item, dict):
            continue
        img = extract_image_url(item, host)
        if not img:
            continue
        title = (
            item.get("name")
            or item.get("category")
            or item.get("type")
            or "Item"
        )
        results.append(
            {
                "image_url": img,
                "thumbnail_url": img,
                "title": str(title),
            }
        )
    return results


def _outfit_label(outfit: dict[str, Any]) -> str:
    bits: list[str] = []
    occasion = outfit.get("occasion")
    if occasion:
        bits.append(str(occasion).title())
    status = outfit.get("status")
    if status:
        bits.append(f"({status})")
    return " ".join(bits) if bits else "Outfit"


def svg_summary(
    title: str,
    lines: Sequence[tuple[str, str]],
    *,
    subtitle: str | None = None,
    accent: str = _DEFAULT_ACCENT,
    width: int = 360,
) -> str:
    """Render a small key/value summary card and return a data: URL."""
    line_h = 26
    pad_x = 22
    header_h = 60 if subtitle else 44
    body_top = header_h + 12
    body_h = max(line_h * max(len(lines), 1), line_h)
    height = body_top + body_h + 16

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
    )
    parts.append(
        f'<rect width="{width}" height="{height}" rx="16" ry="16" fill="{_BG}"/>'
    )
    parts.append(
        f'<path d="M0 16 Q0 0 16 0 H{width - 16} Q{width} 0 {width} 16 V{header_h} '
        f'H0 Z" fill="{accent}"/>'
    )
    parts.append(
        f'<text x="{pad_x}" y="28" font-family="{_FONT}" font-size="17" '
        f'font-weight="700" fill="white">{_esc(_trunc(title, 50))}</text>'
    )
    if subtitle:
        parts.append(
            f'<text x="{pad_x}" y="48" font-family="{_FONT}" font-size="12" '
            f'fill="rgba(255,255,255,0.85)">{_esc(_trunc(subtitle, 60))}</text>'
        )

    for i, (label, value) in enumerate(lines):
        y = body_top + i * line_h + 18
        if i % 2 == 0:
            parts.append(
                f'<rect x="0" y="{y - 18}" width="{width}" '
                f'height="{line_h}" fill="{_BG_ALT}"/>'
            )
        parts.append(
            f'<text x="{pad_x}" y="{y}" font-family="{_FONT}" font-size="12" '
            f'fill="{_MUTED}">{_esc(_trunc(label, 22))}</text>'
        )
        parts.append(
            f'<text x="{width - pad_x}" y="{y}" font-family="{_FONT}" '
            f'font-size="13" font-weight="600" fill="{_FG}" '
            f'text-anchor="end">{_esc(_trunc(value, 22))}</text>'
        )

    parts.append("</svg>")
    return _to_data_url("".join(parts))
