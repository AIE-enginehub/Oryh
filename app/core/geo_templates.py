"""Shipped tables of places a workspace may load once.

`cn_provinces`: China's 34 province-level divisions under a `CN` country
geo, coded by GB/T 2260 (six digits, 330000 for Zhejiang), named in Chinese and English.
Cities and districts are not shipped — a workspace adds the ones it sells
in, and a place nobody named is not invented from an address string.
"""

from __future__ import annotations

# (code, zh name, en name, geo_type, parent code)
CN_PROVINCES: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("CN", "中国", "China", "country", None),
    ("110000", "北京市", "Beijing", "province", "CN"),
    ("120000", "天津市", "Tianjin", "province", "CN"),
    ("130000", "河北省", "Hebei", "province", "CN"),
    ("140000", "山西省", "Shanxi", "province", "CN"),
    ("150000", "内蒙古自治区", "Inner Mongolia", "province", "CN"),
    ("210000", "辽宁省", "Liaoning", "province", "CN"),
    ("220000", "吉林省", "Jilin", "province", "CN"),
    ("230000", "黑龙江省", "Heilongjiang", "province", "CN"),
    ("310000", "上海市", "Shanghai", "province", "CN"),
    ("320000", "江苏省", "Jiangsu", "province", "CN"),
    ("330000", "浙江省", "Zhejiang", "province", "CN"),
    ("340000", "安徽省", "Anhui", "province", "CN"),
    ("350000", "福建省", "Fujian", "province", "CN"),
    ("360000", "江西省", "Jiangxi", "province", "CN"),
    ("370000", "山东省", "Shandong", "province", "CN"),
    ("410000", "河南省", "Henan", "province", "CN"),
    ("420000", "湖北省", "Hubei", "province", "CN"),
    ("430000", "湖南省", "Hunan", "province", "CN"),
    ("440000", "广东省", "Guangdong", "province", "CN"),
    ("450000", "广西壮族自治区", "Guangxi", "province", "CN"),
    ("460000", "海南省", "Hainan", "province", "CN"),
    ("500000", "重庆市", "Chongqing", "province", "CN"),
    ("510000", "四川省", "Sichuan", "province", "CN"),
    ("520000", "贵州省", "Guizhou", "province", "CN"),
    ("530000", "云南省", "Yunnan", "province", "CN"),
    ("540000", "西藏自治区", "Tibet", "province", "CN"),
    ("610000", "陕西省", "Shaanxi", "province", "CN"),
    ("620000", "甘肃省", "Gansu", "province", "CN"),
    ("630000", "青海省", "Qinghai", "province", "CN"),
    ("640000", "宁夏回族自治区", "Ningxia", "province", "CN"),
    ("650000", "新疆维吾尔自治区", "Xinjiang", "province", "CN"),
    ("710000", "台湾省", "Taiwan", "province", "CN"),
    ("810000", "香港特别行政区", "Hong Kong", "province", "CN"),
    ("820000", "澳门特别行政区", "Macao", "province", "CN"),
)

GEO_TEMPLATES: dict[str, tuple[tuple[str, str, str, str, str | None], ...]] = {
    "cn_provinces": CN_PROVINCES,
}
