# -*- coding: utf-8 -*-
"""
hikmah-dataml/brand.py
Brand identity + section taxonomy for HIKMAH DataML.
Merged into the payload by main.py and consumed by the shared base.html.j2.
SECTIONS also drives the offline demo payload (main.py --demo).
"""

BRAND = {
    "product_name":    "HIKMAH DataML",
    "wordmark_main":   "HIKMAH",
    "wordmark_accent": "DataML",
    "eyebrow":         "Weekly MLOps, ML & Data Science Intelligence",
    "tagline":         "Production Intelligence for ML Engineers",
    "ticker_label":    "ML FEED",
    "owner":           "Muhammad Tahir Riaz",
    "website":         "trmtelcocloudai.com",
    "primary":         "#10B981",
    "primary_dark":    "#047857",
    "primary_bg":      "#ECFDF5",
    "accent":          "#F97316",
    "accent_dark":     "#C2410C",
    "icons":           {'s1': '⚙️', 's2': '🔬', 's3': '🔎', 's4': '☁️'},
}

VOLUME  = "I"
EDITION = "Global Edition"

SECTIONS = [{'id': 's1', 'number': '01', 'title': 'MLOps & Platforms', 'eyebrow': 'MLflow · Kubeflow · Feature Stores · Model Registry · CI/CD · Monitoring', 'meta': 'Databricks · MLflow · dbt · Weights & Biases · Evidently AI', 'color_class': 's1'}, {'id': 's2', 'number': '02', 'title': 'ML & Deep Learning', 'eyebrow': 'PyTorch · Fine-Tuning · Transformers · Computer Vision · Time-Series', 'meta': 'PyTorch · HuggingFace · scikit-learn · XGBoost · TensorFlow', 'color_class': 's2'}, {'id': 's3', 'number': '03', 'title': 'RAG, Vector & Data Infrastructure', 'eyebrow': 'RAG Architectures · Vector DBs · Embeddings · LangChain · LlamaIndex', 'meta': 'Weaviate · Pinecone · Chroma · LangChain · Apache Iceberg', 'color_class': 's3'}, {'id': 's4', 'number': '04', 'title': 'Cloud ML: Azure & AWS', 'eyebrow': 'Azure ML · Prompt Flow · SageMaker · Bedrock · Vertex AI · Cost', 'meta': 'Azure ML · SageMaker · Bedrock · Vertex AI · Cost Engineering', 'color_class': 's4'}]
