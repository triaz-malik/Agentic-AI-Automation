# -*- coding: utf-8 -*-
"""
hikmah-cloudinfra/brand.py
Brand identity + section taxonomy for HIKMAH CloudInfra.
Merged into the payload by main.py and consumed by the shared base.html.j2.
SECTIONS also drives the offline demo payload (main.py --demo).
"""

BRAND = {
    "product_name":    "HIKMAH CloudInfra",
    "wordmark_main":   "HIKMAH",
    "wordmark_accent": "CloudInfra",
    "eyebrow":         "Weekly Cloud, Containers & Edge Intelligence",
    "tagline":         "Infrastructure Intelligence for Platform Engineers",
    "ticker_label":    "CLOUD FEED",
    "owner":           "Muhammad Tahir Riaz",
    "website":         "trmtelcocloudai.com",
    "primary":         "#0EA5E9",
    "primary_dark":    "#0369A1",
    "primary_bg":      "#F0F9FF",
    "accent":          "#FB7185",
    "accent_dark":     "#9F1239",
    "icons":           {'s1': '☁️', 's2': '📦', 's3': '🗄️', 's4': '🌐'},
}

VOLUME  = "I"
EDITION = "Global Edition"

SECTIONS = [{'id': 's1', 'number': '01', 'title': 'Cloud Platforms', 'eyebrow': 'AWS · Azure · GCP · Multi-Cloud · IaC · FinOps · Serverless', 'meta': 'AWS · Microsoft Azure · Google Cloud · HashiCorp · Pulumi', 'color_class': 's1'}, {'id': 's2', 'number': '02', 'title': 'Containers & Kubernetes', 'eyebrow': 'Docker · Kubernetes · Helm · Service Mesh · WASM · OCI', 'meta': 'Docker · CNCF · Istio · Cilium · Argo · Crossplane', 'color_class': 's2'}, {'id': 's3', 'number': '03', 'title': 'Databases & Storage', 'eyebrow': 'PostgreSQL · MongoDB · Redis · ClickHouse · S3 · Object Storage', 'meta': 'PostgreSQL · MongoDB · Redis · ClickHouse · Apache Arrow', 'color_class': 's3'}, {'id': 's4', 'number': '04', 'title': 'Edge, CDN & Telecom Cloud', 'eyebrow': 'Edge Compute · CDN · WASM at Edge · MEC · Telecom Cloud · vRAN', 'meta': 'Cloudflare · Fastly · AWS Outposts · Azure Edge · MEC', 'color_class': 's4'}]
