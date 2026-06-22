# -*- coding: utf-8 -*-
"""
hikmah-signal/brand.py
Brand identity + section taxonomy for HIKMAH Signal.
Merged into the payload by main.py and consumed by the shared base.html.j2.
SECTIONS also drives the offline demo payload (main.py --demo).
"""

BRAND = {
    "product_name":    "HIKMAH Signal",
    "wordmark_main":   "HIKMAH",
    "wordmark_accent": "Signal",
    "eyebrow":         "Weekly Telecom, 5G & RAN Intelligence",
    "tagline":         "Network Intelligence for Telecom Engineers",
    "ticker_label":    "NET FEED",
    "owner":           "Muhammad Tahir Riaz",
    "website":         "trmtelcocloudai.com",
    "primary":         "#06B6D4",
    "primary_dark":    "#0E7490",
    "primary_bg":      "#ECFEFF",
    "accent":          "#F59E0B",
    "accent_dark":     "#B45309",
    "icons":           {'s1': '📈', 's2': '📡', 's3': '🤖', 's4': '🛰️'},
}

VOLUME  = "II"
EDITION = "GCC & Global Edition"

SECTIONS = [{'id': 's1', 'number': '01', 'title': 'Market & Operators', 'eyebrow': 'Coverage · M&A · Spectrum Deals · Vendor Financials', 'meta': 'Ericsson · Nokia · Huawei · ZTE · Regional Operators', 'color_class': 's1'}, {'id': 's2', 'number': '02', 'title': 'Network Infrastructure', 'eyebrow': '5G-Adv · 6G · O-RAN · CU/DU · CloudRAN · Private 5G', 'meta': 'RAN Architecture · Transport · Core · Edge', 'color_class': 's2'}, {'id': 's3', 'number': '03', 'title': 'AI, Standards & Analytics', 'eyebrow': '3GPP Rel-18/19 · GSMA APIs · AI/ML RAN · Ookla', 'meta': 'Machine Learning · Automation · Performance Intelligence', 'color_class': 's3'}, {'id': 's4', 'number': '04', 'title': 'Spectrum, Satellite & Regulation', 'eyebrow': 'NTN · ITU · Cybersec · Fiber · Satellite · Regulation', 'meta': 'Policy · Licensing · NTN Integration · Critical Infrastructure', 'color_class': 's4'}]
