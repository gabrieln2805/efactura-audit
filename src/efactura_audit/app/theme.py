"""Chart colors and layout shared by the app's tabs.

Values are the dataviz reference palette: categorical slot 1 for single-series marks, the fixed
status palette for flag severity (always shown with its icon and label), and a single-hue blue ramp
for magnitude. Gridlines and axes are solid hairlines.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

BLUE = "#2a78d6"
SEV_COLORS = {"high": "#d03b3b", "medium": "#ec835a", "low": "#fab219"}
MUTED = "#898781"
# sequential: one blue whose opacity grows with the value, on a transparent plot, so near-zero recedes into
# whichever surface is showing (light or dark) without having to know the theme
SEQUENTIAL = [[0.0, "rgba(42,120,214,0.10)"], [1.0, "rgba(42,120,214,1.0)"]]


def is_dark() -> bool:
    # an explicitly configured theme wins; otherwise the browser's, which Streamlit only learns after the
    # first run (it reports "light" until then)
    base = st.get_option("theme.base")
    if base in ("light", "dark"):
        return base == "dark"
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 - no browser session (tests)
        return False


def surface() -> str:
    """Page background, for the 2px ring around overlapping markers."""
    return "#0e1117" if is_dark() else "#ffffff"


def chart_layout(fig: go.Figure, height: int = 280, lang: str | None = None) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", showlegend=False, font=dict(size=12),
                      hoverlabel=dict(font_size=12), bargap=0.45)
    if lang:   # decimal and thousands separators in hover labels and ticks
        fig.update_layout(separators=",." if lang == "ro" else ".,")
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return fig
