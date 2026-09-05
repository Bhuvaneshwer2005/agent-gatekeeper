# Tests for the hand-drawn icon set - just confirms every icon actually
# used elsewhere in the app renders valid, well-formed SVG, since a typo
# in an icon name would otherwise only surface as a blank spot on a page.

import pytest

from icons import _PATHS, icon, icon_inline

USED_ICON_NAMES = [
    "shield",
    "trending-up",
    "play",
    "flask",
    "folder",
    "home",
    "refresh",
    "check-circle",
    "x-circle",
    "info-circle",
    "robot",
    "credit-card",
    "scale",
    "tag",
    "clipboard",
    "arrow-right",
]


def test_every_icon_used_elsewhere_is_actually_defined():
    for name in USED_ICON_NAMES:
        assert name in _PATHS


@pytest.mark.parametrize("name", USED_ICON_NAMES)
def test_icon_renders_well_formed_svg(name):
    svg = icon(name)
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "{color}" not in svg  # every path placeholder must have been filled in


def test_icon_respects_size_and_color():
    svg = icon("shield", size=32, color="#3B82F6")
    assert 'width="32"' in svg
    assert 'height="32"' in svg
    assert "#3B82F6" in svg


def test_icon_inline_defaults_to_smaller_size():
    svg = icon_inline("check-circle")
    assert 'width="18"' in svg


def test_unknown_icon_name_raises_instead_of_rendering_nothing():
    with pytest.raises(KeyError):
        icon("does-not-exist")
