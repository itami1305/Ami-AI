"""Dataclass tỉ lệ layout — tránh circular import giữa layout_regions và vision."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutRatios:
    sidebar: float
    right: float
    inner_top: float
    bottom: float
