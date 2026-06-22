# -*- coding: utf-8 -*-
"""
hikmah-dataarch/brand.py
Brand identity + section taxonomy for HIKMAH DataArch.
Merged into the payload by main.py and consumed by the shared base.html.j2.
SECTIONS also drives the offline demo payload (main.py --demo).
"""

BRAND = {
    "product_name":    "HIKMAH DataArch",
    "wordmark_main":   "HIKMAH",
    "wordmark_accent": "DataArch",
    "eyebrow":         "Weekly Databases, Big Data, GPUs & API Intelligence",
    "tagline":         "Architecture Intelligence for Systems Engineers",
    "ticker_label":    "DATA FEED",
    "owner":           "Muhammad Tahir Riaz",
    "website":         "trmtelcocloudai.com",
    "primary":         "#A855F7",
    "primary_dark":    "#6B21A8",
    "primary_bg":      "#F3E8FF",
    "accent":          "#FB7185",
    "accent_dark":     "#9F1239",
    "icons":           {'s1': '🏛️', 's2': '🌊', 's3': '⚡', 's4': '🔌'},
}

VOLUME  = "I"
EDITION = "Global Edition"

SECTIONS = [{'id': 's1', 'number': '01', 'title': 'Database Architecture', 'eyebrow': 'Serverless DB · HTAP · NewSQL · Multi-Model · Schema Design · Replication', 'meta': 'Neon · Supabase · TiDB · CockroachDB · Turso · PlanetScale', 'color_class': 's1'}, {'id': 's2', 'number': '02', 'title': 'Big Data & Streaming', 'eyebrow': 'Kafka · Flink · Spark · Delta Lake · Data Lakehouse · CDC', 'meta': 'Apache Kafka · Flink · Spark · Databricks · Confluent', 'color_class': 's2'}, {'id': 's3', 'number': '03', 'title': 'GPUs & Compute', 'eyebrow': 'NVIDIA · AMD · Groq · Inference Chips · CUDA · Inference Serving', 'meta': 'NVIDIA · AMD · Groq · Cerebras · vLLM · TensorRT-LLM', 'color_class': 's3'}, {'id': 's4', 'number': '04', 'title': 'APIs & Automation', 'eyebrow': 'REST · GraphQL · gRPC · API Gateway · Workflow Automation · Temporal', 'meta': 'Stripe · Kong · Temporal · n8n · GraphQL · OpenAPI', 'color_class': 's4'}]
