"""Shipped tables of places a workspace may load once.

`cn_provinces`: China's 34 province-level divisions under a `CN` country
geo, coded by GB/T 2260 (six digits, 330000 for Zhejiang), named in Chinese and English.
Cities and districts are not shipped — a workspace adds the ones it sells
in, and a place nobody named is not invented from an address string.
"""

from __future__ import annotations

from app.locales.zh_CN.geos import CN_PROVINCES as _CN_PROVINCES_ZH

# (code, zh name, en name, geo_type, parent code)
CN_PROVINCES: tuple[tuple[str, str, str, str, str | None], ...] = _CN_PROVINCES_ZH

GEO_TEMPLATES: dict[str, tuple[tuple[str, str, str, str, str | None], ...]] = {
    "cn_provinces": CN_PROVINCES,
}
