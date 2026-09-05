# A small hand-drawn vector icon set, used everywhere the app renders its
# own HTML directly (the homepage, Live Demo's step list, the Stress Test
# result badges) - anywhere Streamlit doesn't force a choice between an
# emoji and its own built-in Material Symbols glyph set.
#
# Deliberately minimal, consistent line icons (24x24, currentColor stroke)
# rather than pulling in an icon font or CDN - no extra network dependency,
# no version to go stale, and the whole set is small enough to read in one
# file.

from typing import Optional

_PATHS = {
    "shield": '<path d="M12 2 L20 6 V11 C20 16 16.5 20 12 22 C7.5 20 4 16 4 11 V6 Z" />',
    "trending-up": (
        '<polyline points="3 17 9 11 13 15 21 6" />'
        '<polyline points="15 6 21 6 21 12" />'
    ),
    "play": '<polygon points="6 4 20 12 6 20" fill="{color}" stroke="none" />',
    "flask": (
        '<path d="M9 2 H15" />'
        '<path d="M10 2 V8 L4 19 A2 2 0 0 0 6 22 H18 A2 2 0 0 0 20 19 L14 8 V2" />'
    ),
    "folder": '<path d="M3 6 a2 2 0 0 1 2-2 h4 l2 2 h8 a2 2 0 0 1 2 2 v9 a2 2 0 0 1 -2 2 H5 a2 2 0 0 1 -2-2 Z" />',
    "home": '<path d="M4 11 L12 4 L20 11 V20 A1 1 0 0 1 19 21 H5 A1 1 0 0 1 4 20 Z" /><path d="M9 21 V14 H15 V21" />',
    "refresh": '<path d="M21 12a9 9 0 1 1-3-6.7" /><polyline points="21 3 21 9 15 9" />',
    "check-circle": '<circle cx="12" cy="12" r="9" /><polyline points="8 12 11 15 16 9" />',
    "x-circle": '<circle cx="12" cy="12" r="9" /><line x1="9" y1="9" x2="15" y2="15" /><line x1="15" y1="9" x2="9" y2="15" />',
    "info-circle": '<circle cx="12" cy="12" r="9" /><line x1="12" y1="11" x2="12" y2="16" /><circle cx="12" cy="7.5" r="0.9" fill="{color}" stroke="none" />',
    "robot": (
        '<rect x="5" y="8" width="14" height="10" rx="2" />'
        '<circle cx="9" cy="13" r="1.2" fill="{color}" stroke="none" />'
        '<circle cx="15" cy="13" r="1.2" fill="{color}" stroke="none" />'
        '<line x1="12" y1="8" x2="12" y2="4" />'
        '<circle cx="12" cy="3" r="1" fill="{color}" stroke="none" />'
    ),
    "credit-card": '<rect x="2" y="5" width="20" height="14" rx="2" /><line x1="2" y1="10" x2="22" y2="10" />',
    "scale": '<path d="M12 3 v4" /><path d="M4 7 h16" /><circle cx="4" cy="14" r="4" /><circle cx="20" cy="14" r="4" />',
    "tag": (
        '<path d="M20.59 13.41 L13.42 20.58 a2 2 0 0 1 -2.83 0 L2 12 V2 h10 l8.59 8.59 '
        'a2 2 0 0 1 0 2.82 Z" />'
        '<circle cx="6.5" cy="6.5" r="1.2" fill="{color}" stroke="none" />'
    ),
    "clipboard": (
        '<rect x="6" y="4" width="12" height="16" rx="2" />'
        '<rect x="9" y="2" width="6" height="4" rx="1" />'
        '<line x1="9" y1="11" x2="15" y2="11" />'
        '<line x1="9" y1="15" x2="15" y2="15" />'
    ),
    "arrow-right": '<line x1="4" y1="12" x2="20" y2="12" /><polyline points="14 6 20 12 14 18" />',
}


def icon(name: str, size: int = 24, color: str = "currentColor", stroke_width: float = 2) -> str:
    """Render one icon as a standalone <svg> string.

    Every icon shares the same 24x24 viewBox and stroke style, so mixing
    them in one row or card never looks inconsistent - the only per-icon
    variation is the path data itself.
    """
    path = _PATHS[name].format(color=color)
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round" style="vertical-align: middle;">{path}</svg>'
    )


def icon_inline(name: str, size: int = 18, color: Optional[str] = None) -> str:
    """An icon sized and colored for sitting inline next to a line of text."""
    return icon(name, size=size, color=color or "currentColor", stroke_width=2.2)
