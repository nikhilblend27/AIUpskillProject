# NewsFilterAgent — Evaluation Report

- **Date:** 2026-11-20 13:59
- **Model:** `gemini/gemini-3.5-flash`
- **Dataset:** `golden_dataset.json` (v1.1, 20 cases)
- **Relevance threshold:** 6/10

## Metrics

| Metric | Value |
|---|---|
| Accuracy | 100.0% (20/20) |
| Precision | 100.0% |
| Recall | 100.0% |
| F1 score | 1.000 |
| Score MAE (0-10) | 0.40 |

## Confusion matrix

| | Predicted relevant | Predicted not relevant |
|---|---|---|
| **Actually relevant** | 11 (TP) | 0 (FN) |
| **Actually not relevant** | 0 (FP) | 9 (TN) |

## Per-case results

| # | Result | Title | Expected | Predicted (score) | Model reasoning |
|---|---|---|---|---|---|
| 1 | ✅ | GPT-4 Released by OpenAI | Relevant (10) | Relevant (10) | Major foundation LLM release from OpenAI. |
| 2 | ✅ | New JavaScript Framework Released | Not (1) | Not (1) | Web development framework update with no AI angle. |
| 3 | ✅ | Machine Learning in Healthcare Breakthrough | Relevant (9) | Relevant (8) | Significant deep learning research breakthrough in healthcare. |
| 4 | ✅ | Docker 25 Released | Not (2) | Not (1) | General developer software release with no AI focus. |
| 5 | ✅ | Stable Diffusion 3.0 Improves Image Generation | Relevant (10) | Relevant (10) | Major release of a popular open-weight text-to-image model. |
| 6 | ✅ | PostgreSQL 16 Features | Not (1) | Not (1) | Database feature announcement without AI infrastructure context. |
| 7 | ✅ | Neural Network Optimizes Traffic Flow | Relevant (8) | Relevant (7) | Real-world application of neural networks for smart infrastructure. |
| 8 | ✅ | Recipe for Perfect Pizza Dough | Not (0) | Not (0) | Cooking content completely unrelated to technology or AI. |
| 9 | ✅ | Transformer Architecture Explained | Relevant (9) | Relevant (9) | Deep dive into core neural network architecture for NLP. |
| 10 | ✅ | AI Ethics Guidelines Published | Relevant (7) | Relevant (7) | Guidelines focused on responsible AI development and ethics. |
| 11 | ✅ | Nvidia unveils next-generation data center GPU | Relevant (8) | Relevant (9) | Major hardware release designed specifically for AI training and inference workloads. |
| 12 | ✅ | Smart fridge now has an 'AI' button | Not (3) | Not (2) | Consumer appliance with a superficial AI label and no meaningful ML technical depth. |
| 13 | ✅ | EU finalises rules for general-purpose AI models | Relevant (8) | Relevant (8) | Major AI policy and regulatory news affecting foundation model providers. |
| 14 | ✅ | Rust 2.0 roadmap announced | Not (1) | Not (1) | General software engineering and programming language news without an AI context. |
| 15 | ✅ | Building a RAG chatbot over your company docs | Relevant (8) | Relevant (8) | Practical technical guide on building LLM applications using RAG and vector stores. |
| 16 | ✅ | Kubernetes 1.40 adds sidecar improvements | Not (1) | Not (1) | General cloud infrastructure and DevOps news unrelated to machine learning. |
| 17 | ✅ | Open-source speech recognition model beats Whisper | Relevant (9) | Relevant (9) | Notable open-source speech recognition model release advancing ASR benchmarks. |
| 18 | ✅ | Critical vulnerability found in OpenSSL | Not (1) | Not (0) | General cybersecurity news with no machine learning angle. |
| 19 | ✅ | Self-driving startup expands robotaxi service | Relevant (7) | Relevant (8) | Commercial deployment of computer vision and AI-powered autonomous vehicles. |
| 20 | ✅ | Smartphone review: best battery life of the year | Not (1) | Not (0) | Consumer hardware gadget review with no relevance to AI. |

## Failure analysis

No misclassifications on this dataset.
