#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
District mapping from CSV location/neighborhood names to 
Hong Kong's 18 administrative districts (matching official GeoJSON).
"""

# Mapping from CSV neighborhood/area names to the 18 HK administrative districts
# Based on Hong Kong administrative district boundaries
NEIGHBORHOOD_TO_DISTRICT = {
    # Central & Western
    "kennedy town": "Central & Western",
    "the peak": "Central & Western",
    "mid levels": "Central & Western",
    "central": "Central & Western",
    "sheung wan": "Central & Western",
    "sai ying pun": "Central & Western",
    "admiralty": "Central & Western",
    
    # Wan Chai
    "happy valley": "Wan Chai",
    "wan chai": "Wan Chai",
    "causeway bay": "Wan Chai",
    "jardines lookout": "Wan Chai",
    
    # Eastern
    "north point": "Eastern",
    "chai wan": "Eastern",
    "shau kei wan": "Eastern",
    "quarry bay": "Eastern",
    "taikoo shing": "Eastern",
    "sai wan ho": "Eastern",
    "heng fa chuen": "Eastern",
    "shek o": "Eastern",
    
    # Southern
    "aberdeen": "Southern",
    "ap lei chau": "Southern",
    "pok fu lam": "Southern",
    "pokfulam": "Southern",
    "repulse bay": "Southern",
    "stanley": "Southern",
    "wong chuk hang": "Southern",
    "ocean park": "Southern",
    "chung hom kok": "Southern",
    
    # Yau Tsim Mong
    "yau ma tei": "Yau Tsim Mong",
    "mong kok": "Yau Tsim Mong",
    "tsim sha tsui": "Yau Tsim Mong",
    "jordan": "Yau Tsim Mong",
    "king's park": "Yau Tsim Mong",
    
    # Sham Shui Po
    "sham shui po": "Sham Shui Po",
    "lichfield": "Sham Shui Po",
    "cheung sha wan": "Sham Shui Po",
    "lai chi kok": "Sham Shui Po",
    "shek kip mei": "Sham Shui Po",
    
    # Kowloon City
    "kowloon city": "Kowloon City",
    "kowloon tong": "Kowloon City",
    "hung hom": "Kowloon City",
    "to kwa wan": "Kowloon City",
    "whampoa": "Kowloon City",
    
    # Wong Tai Sin
    "ngau chi wan": "Wong Tai Sin",
    "wong tai sin": "Wong Tai Sin",
    "lok fu": "Wong Tai Sin",
    "choi hung": "Wong Tai Sin",
    "diamond hill": "Wong Tai Sin",
    "fung tak": "Wong Tai Sin",
    "wang tau hom": "Wong Tai Sin",
    "tsz wan shan": "Wong Tai Sin",
    
    # Kwun Tong
    "kwun tong": "Kwun Tong",
    "lam tin": "Kwun Tong",
    "ngau tau kok": "Kwun Tong",
    "sau mau ping": "Kwun Tong",
    "yau tong": "Kwun Tong",
    "kowloon bay": "Kwun Tong",
    "jordan valley": "Kwun Tong",
    
    # Tsuen Wan
    "tsuen wan east": "Tsuen Wan",
    "tsuen wan west": "Tsuen Wan",
    "tsuen wan": "Tsuen Wan",
    
    # Tuen Mun
    "tuen mun": "Tuen Mun",
    "tuen mun central": "Tuen Mun",
    "tuen mun north": "Tuen Mun",
    "tuen mun south": "Tuen Mun",
    "siu lam": "Tuen Mun",
    "so kwun wat": "Tuen Mun",
    
    # Yuen Long
    "yuen long": "Yuen Long",
    "tin shui wai": "Yuen Long",
    "kam tin": "Yuen Long",
    "pat heung": "Yuen Long",
    "ha tsuen": "Yuen Long",
    "lok ma chau": "Yuen Long",
    
    # North
    "sheung shui": "North",
    "fan ling": "North",
    "ta kwu ling": "North",
    "sha tau kok": "North",
    
    # Tai Po
    "tai po": "Tai Po",
    "tai po market": "Tai Po",
    "tai mei tuk": "Tai Po",
    
    # Sai Kung
    "sai kung": "Sai Kung",
    "tseung kwan o": "Sai Kung",
    "clear water bay": "Sai Kung",
    "hang hau": "Sai Kung",
    
    # Sha Tin
    "sha tin": "Sha Tin",
    "ma on shan": "Sha Tin",
    "tai wai": "Sha Tin",
    "fo tan": "Sha Tin",
    "siu lek yuen": "Sha Tin",
    "tsu leck yuen": "Sha Tin",
    "tsui lek yuen": "Sha Tin",
    
    # Kwai Tsing
    "kwai chung": "Kwai Tsing",
    "ha kwai chung": "Kwai Tsing",
    "sheung kwai chung": "Kwai Tsing",
    "tsing yi": "Kwai Tsing",
    "kwai fong": "Kwai Tsing",
    "kwai hing": "Kwai Tsing",
    
    # Islands
    "tung chung": "Islands",
    "mui wo": "Islands",
    "yam o": "Islands",
    "discovery bay": "Islands",
    "peng chau": "Islands",
    "lamma island": "Islands",
    "cheung chau": "Islands",
    "tai o": "Islands",
}

# 香港 18 官方行政区名列表
OFFICIAL_DISTRICTS = [
    "Central & Western",
    "Wan Chai",
    "Eastern",
    "Southern",
    "Yau Tsim Mong",
    "Sham Shui Po",
    "Kowloon City",
    "Wong Tai Sin",
    "Kwun Tong",
    "Tsuen Wan",
    "Tuen Mun",
    "Yuen Long",
    "North",
    "Tai Po",
    "Sai Kung",
    "Sha Tin",
    "Kwai Tsing",
    "Islands",
]

_LOOKUP = {}
for _k, _v in NEIGHBORHOOD_TO_DISTRICT.items():
    _key = _k.lower().strip()
    _LOOKUP[_key] = _v
    _LOOKUP[_key.replace(" ", "")] = _v

for _d in OFFICIAL_DISTRICTS:
    _low = _d.lower()
    _LOOKUP[_low] = _d
    _LOOKUP[_low.replace(" ", "")] = _d
    _LOOKUP[_low.replace("&", "and")] = _d
    _LOOKUP[_low.replace("&", "and").replace(" ", "")] = _d


def get_big_district(raw) -> str:
    """
    根据原始地点/区名查找对应的香港 18 官方行政大区名称 (big_district)。
    若未识别或为空则返回空字符串。
    """
    if raw is None:
        return ""
    name = str(raw).strip().lower()
    if not name or name in ("nan", "none", "null"):
        return ""

    if name in _LOOKUP:
        return _LOOKUP[name]

    no_space = name.replace(" ", "")
    if no_space in _LOOKUP:
        return _LOOKUP[no_space]

    for token in ("&", "and", "-"):
        variant = name.replace(token, " ")
        if variant in _LOOKUP:
            return _LOOKUP[variant]
        if variant.replace(" ", "") in _LOOKUP:
            return _LOOKUP[variant.replace(" ", "")]

    return ""

