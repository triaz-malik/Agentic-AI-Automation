# -*- coding: utf-8 -*-
"""
hikmah-intelligence/brand.py
Brand identity + section taxonomy for HIKMAH Intelligence.
Merged into the payload by main.py and consumed by the shared base.html.j2.
SECTIONS also drives the offline demo payload (main.py --demo).
"""

BRAND = {
    "product_name":    "HIKMAH Intelligence",
    "wordmark_main":   "HIKMAH",
    "wordmark_accent": "Intelligence",
    "eyebrow":         "Weekly AI, Agentic & LLM Intelligence",
    "tagline":         "Frontier Intelligence for AI Builders",
    "ticker_label":    "AI FEED",
    "owner":           "Muhammad Tahir Riaz",
    "website":         "trmtelcocloudai.com",
    "primary":         "#6366F1",
    "primary_dark":    "#4338CA",
    "primary_bg":      "#EEF2FF",
    "accent":          "#10B981",
    "accent_dark":     "#047857",
    "icons":           {'s1': '🧠', 's2': '🤖', 's3': '🏭', 's4': '🛡️'},
}

VOLUME  = "I"
EDITION = "GCC & Global Edition"

SECTIONS = [{'id': 's1', 'number': '01', 'title': 'Models & Research', 'eyebrow': 'Foundation Models · Benchmarks · Architecture · Multimodal', 'meta': 'Anthropic · OpenAI · Google DeepMind · Meta · Mistral', 'color_class': 's1'}, {'id': 's2', 'number': '02', 'title': 'Agentic & Tools', 'eyebrow': 'Agentic Frameworks · MCP · Orchestration · CrewAI · LangGraph', 'meta': 'Multi-Agent Systems · Workflow Automation · Developer Tooling', 'color_class': 's2'}, {'id': 's3', 'number': '03', 'title': 'Industry & Deployments', 'eyebrow': 'Enterprise AI · GCC Deployments · Telecom AI · Healthcare', 'meta': 'Real-World Implementations · ROI · Use Cases · MENA Region', 'color_class': 's3'}, {'id': 's4', 'number': '04', 'title': 'Policy, Safety & Infrastructure', 'eyebrow': 'AI Safety · Regulation · GPU Infrastructure · Open Source', 'meta': 'EU AI Act · NIST · Compute · Alignment', 'color_class': 's4'}]
