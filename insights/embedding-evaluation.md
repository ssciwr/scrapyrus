# Embedding Evaluations

## Scope

- Requested paired-record sample: 1000
- Sample seed: 0

## Summary

| Model | Transcriptions | Translations | Paired | Dimensions | recall@1 | recall@2 | recall@3 | recall@4 | recall@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `BAAI/bge-m3` | 996 | 999 | 995 | 1024 | 80.00% | 85.73% | 88.44% | 89.75% | 91.06% |
| `codestral-embed-2505` | 996 | 999 | 995 | 1536 | 89.85% | 93.47% | 94.37% | 94.77% | 94.87% |
| `google/embeddinggemma-300m` | 996 | 999 | 995 | 768 | 38.79% | 49.15% | 54.77% | 57.89% | 60.70% |
| `ibm-granite/granite-embedding-311m-multilingual-r2` | 996 | 999 | 995 | 768 | 23.92% | 31.96% | 37.79% | 41.01% | 43.82% |
| `mistral-embed-2312` | 996 | 999 | 995 | 1024 | 49.25% | 57.89% | 62.61% | 64.92% | 66.83% |
| `Qwen/Qwen3-Embedding-0.6B` | 996 | 999 | 995 | 1024 | 70.95% | 78.19% | 80.90% | 83.02% | 84.42% |
| `Qwen/Qwen3-Embedding-4B` | 996 | 999 | 995 | 2560 | 90.35% | 93.07% | 93.77% | 94.57% | 95.08% |
| `Qwen/Qwen3-Embedding-8B` | 996 | 999 | 995 | 4096 | 93.67% | 96.58% | 97.39% | 97.69% | 97.89% |
| `text-embedding-3-large` | 996 | 999 | 995 | 3072 | 81.81% | 88.14% | 90.65% | 92.76% | 93.37% |
| `text-embedding-3-small` | 996 | 999 | 995 | 1536 | 24.72% | 34.57% | 38.39% | 42.01% | 45.03% |
| `text-embedding-ada-002` | 996 | 999 | 995 | 1536 | 32.16% | 39.20% | 44.52% | 48.04% | 50.45% |
| `voyage-4` | 996 | 999 | 995 | 1024 | 89.75% | 93.07% | 94.47% | 94.57% | 95.28% |
| `voyage-4-large` | 996 | 999 | 995 | 1024 | 93.37% | 96.08% | 96.78% | 97.39% | 97.39% |
| `voyage-4-lite` | 996 | 999 | 995 | 1024 | 80.80% | 85.03% | 87.04% | 89.15% | 89.95% |

## Embedding Evaluation: `BAAI/bge-m3`

### Scope

- Model: `BAAI/bge-m3`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 796 | 995 | 80.00% |
| recall@2 | 853 | 995 | 85.73% |
| recall@3 | 880 | 995 | 88.44% |
| recall@4 | 893 | 995 | 89.75% |
| recall@5 | 906 | 995 | 91.06% |
| MRR | 845.7290 | 995 | 85.00% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 1 | 18 | 5.56% |
| coptic | recall@2 | 2 | 18 | 11.11% |
| coptic | recall@3 | 5 | 18 | 27.78% |
| coptic | recall@4 | 7 | 18 | 38.89% |
| coptic | recall@5 | 7 | 18 | 38.89% |
| coptic | MRR | 3.3184 | 18 | 18.44% |
| greek | recall@1 | 790 | 971 | 81.36% |
| greek | recall@2 | 846 | 971 | 87.13% |
| greek | recall@3 | 869 | 971 | 89.50% |
| greek | recall@4 | 880 | 971 | 90.63% |
| greek | recall@5 | 893 | 971 | 91.97% |
| greek | MRR | 837.0772 | 971 | 86.21% |
| latin | recall@1 | 3 | 4 | 75.00% |
| latin | recall@2 | 3 | 4 | 75.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 3.3333 | 4 | 83.33% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 779 | 966 | 80.64% |
| 1 chunk | recall@2 | 833 | 966 | 86.23% |
| 1 chunk | recall@3 | 859 | 966 | 88.92% |
| 1 chunk | recall@4 | 872 | 966 | 90.27% |
| 1 chunk | recall@5 | 884 | 966 | 91.51% |
| 1 chunk | MRR | 826.1893 | 966 | 85.53% |
| 2-3 chunks | recall@1 | 14 | 21 | 66.67% |
| 2-3 chunks | recall@2 | 17 | 21 | 80.95% |
| 2-3 chunks | recall@3 | 18 | 21 | 85.71% |
| 2-3 chunks | recall@4 | 18 | 21 | 85.71% |
| 2-3 chunks | recall@5 | 18 | 21 | 85.71% |
| 2-3 chunks | MRR | 15.9525 | 21 | 75.96% |
| 4+ chunks | recall@1 | 3 | 8 | 37.50% |
| 4+ chunks | recall@2 | 3 | 8 | 37.50% |
| 4+ chunks | recall@3 | 3 | 8 | 37.50% |
| 4+ chunks | recall@4 | 3 | 8 | 37.50% |
| 4+ chunks | recall@5 | 4 | 8 | 50.00% |
| 4+ chunks | MRR | 3.5873 | 8 | 44.84% |

## Embedding Evaluation: `codestral-embed-2505`

### Scope

- Model: `codestral-embed-2505`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1077
- Translation chunks: 1162
- Multi-chunk transcriptions: 21
- Multi-chunk translations: 133
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 894 | 995 | 89.85% |
| recall@2 | 930 | 995 | 93.47% |
| recall@3 | 939 | 995 | 94.37% |
| recall@4 | 943 | 995 | 94.77% |
| recall@5 | 944 | 995 | 94.87% |
| MRR | 918.3038 | 995 | 92.29% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 3 | 18 | 16.67% |
| coptic | recall@2 | 3 | 18 | 16.67% |
| coptic | recall@3 | 3 | 18 | 16.67% |
| coptic | recall@4 | 3 | 18 | 16.67% |
| coptic | recall@5 | 3 | 18 | 16.67% |
| coptic | MRR | 3.2640 | 18 | 18.13% |
| greek | recall@1 | 885 | 971 | 91.14% |
| greek | recall@2 | 921 | 971 | 94.85% |
| greek | recall@3 | 930 | 971 | 95.78% |
| greek | recall@4 | 934 | 971 | 96.19% |
| greek | recall@5 | 935 | 971 | 96.29% |
| greek | MRR | 909.0397 | 971 | 93.62% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 877 | 974 | 90.04% |
| 1 chunk | recall@2 | 912 | 974 | 93.63% |
| 1 chunk | recall@3 | 920 | 974 | 94.46% |
| 1 chunk | recall@4 | 924 | 974 | 94.87% |
| 1 chunk | recall@5 | 924 | 974 | 94.87% |
| 1 chunk | MRR | 900.2643 | 974 | 92.43% |
| 2-3 chunks | recall@1 | 11 | 14 | 78.57% |
| 2-3 chunks | recall@2 | 12 | 14 | 85.71% |
| 2-3 chunks | recall@3 | 12 | 14 | 85.71% |
| 2-3 chunks | recall@4 | 12 | 14 | 85.71% |
| 2-3 chunks | recall@5 | 13 | 14 | 92.86% |
| 2-3 chunks | MRR | 11.7061 | 14 | 83.62% |
| 4+ chunks | recall@1 | 6 | 7 | 85.71% |
| 4+ chunks | recall@2 | 6 | 7 | 85.71% |
| 4+ chunks | recall@3 | 7 | 7 | 100.00% |
| 4+ chunks | recall@4 | 7 | 7 | 100.00% |
| 4+ chunks | recall@5 | 7 | 7 | 100.00% |
| 4+ chunks | MRR | 6.3333 | 7 | 90.48% |

## Embedding Evaluation: `google/embeddinggemma-300m`

### Scope

- Model: `google/embeddinggemma-300m`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 386 | 995 | 38.79% |
| recall@2 | 489 | 995 | 49.15% |
| recall@3 | 545 | 995 | 54.77% |
| recall@4 | 576 | 995 | 57.89% |
| recall@5 | 604 | 995 | 60.70% |
| MRR | 488.0993 | 995 | 49.06% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 1 | 18 | 5.56% |
| coptic | recall@2 | 1 | 18 | 5.56% |
| coptic | recall@3 | 1 | 18 | 5.56% |
| coptic | recall@4 | 1 | 18 | 5.56% |
| coptic | recall@5 | 1 | 18 | 5.56% |
| coptic | MRR | 1.2494 | 18 | 6.94% |
| greek | recall@1 | 380 | 971 | 39.13% |
| greek | recall@2 | 483 | 971 | 49.74% |
| greek | recall@3 | 539 | 971 | 55.51% |
| greek | recall@4 | 570 | 971 | 58.70% |
| greek | recall@5 | 598 | 971 | 61.59% |
| greek | MRR | 481.7666 | 971 | 49.62% |
| latin | recall@1 | 3 | 4 | 75.00% |
| latin | recall@2 | 3 | 4 | 75.00% |
| latin | recall@3 | 3 | 4 | 75.00% |
| latin | recall@4 | 3 | 4 | 75.00% |
| latin | recall@5 | 3 | 4 | 75.00% |
| latin | MRR | 3.0833 | 4 | 77.08% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 376 | 966 | 38.92% |
| 1 chunk | recall@2 | 477 | 966 | 49.38% |
| 1 chunk | recall@3 | 531 | 966 | 54.97% |
| 1 chunk | recall@4 | 561 | 966 | 58.07% |
| 1 chunk | recall@5 | 588 | 966 | 60.87% |
| 1 chunk | MRR | 475.2781 | 966 | 49.20% |
| 2-3 chunks | recall@1 | 10 | 21 | 47.62% |
| 2-3 chunks | recall@2 | 11 | 21 | 52.38% |
| 2-3 chunks | recall@3 | 13 | 21 | 61.90% |
| 2-3 chunks | recall@4 | 14 | 21 | 66.67% |
| 2-3 chunks | recall@5 | 14 | 21 | 66.67% |
| 2-3 chunks | MRR | 11.8811 | 21 | 56.58% |
| 4+ chunks | recall@1 | 0 | 8 | 0.00% |
| 4+ chunks | recall@2 | 1 | 8 | 12.50% |
| 4+ chunks | recall@3 | 1 | 8 | 12.50% |
| 4+ chunks | recall@4 | 1 | 8 | 12.50% |
| 4+ chunks | recall@5 | 2 | 8 | 25.00% |
| 4+ chunks | MRR | 0.9402 | 8 | 11.75% |

## Embedding Evaluation: `ibm-granite/granite-embedding-311m-multilingual-r2`

### Scope

- Model: `ibm-granite/granite-embedding-311m-multilingual-r2`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 238 | 995 | 23.92% |
| recall@2 | 318 | 995 | 31.96% |
| recall@3 | 376 | 995 | 37.79% |
| recall@4 | 408 | 995 | 41.01% |
| recall@5 | 436 | 995 | 43.82% |
| MRR | 335.3347 | 995 | 33.70% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 0 | 18 | 0.00% |
| coptic | recall@2 | 0 | 18 | 0.00% |
| coptic | recall@3 | 0 | 18 | 0.00% |
| coptic | recall@4 | 0 | 18 | 0.00% |
| coptic | recall@5 | 1 | 18 | 5.56% |
| coptic | MRR | 0.2283 | 18 | 1.27% |
| greek | recall@1 | 235 | 971 | 24.20% |
| greek | recall@2 | 315 | 971 | 32.44% |
| greek | recall@3 | 373 | 971 | 38.41% |
| greek | recall@4 | 405 | 971 | 41.71% |
| greek | recall@5 | 432 | 971 | 44.49% |
| greek | MRR | 332.0357 | 971 | 34.20% |
| latin | recall@1 | 1 | 4 | 25.00% |
| latin | recall@2 | 1 | 4 | 25.00% |
| latin | recall@3 | 1 | 4 | 25.00% |
| latin | recall@4 | 1 | 4 | 25.00% |
| latin | recall@5 | 1 | 4 | 25.00% |
| latin | MRR | 1.0707 | 4 | 26.77% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 231 | 966 | 23.91% |
| 1 chunk | recall@2 | 308 | 966 | 31.88% |
| 1 chunk | recall@3 | 364 | 966 | 37.68% |
| 1 chunk | recall@4 | 396 | 966 | 40.99% |
| 1 chunk | recall@5 | 422 | 966 | 43.69% |
| 1 chunk | MRR | 324.8959 | 966 | 33.63% |
| 2-3 chunks | recall@1 | 5 | 21 | 23.81% |
| 2-3 chunks | recall@2 | 7 | 21 | 33.33% |
| 2-3 chunks | recall@3 | 7 | 21 | 33.33% |
| 2-3 chunks | recall@4 | 7 | 21 | 33.33% |
| 2-3 chunks | recall@5 | 9 | 21 | 42.86% |
| 2-3 chunks | MRR | 7.2401 | 21 | 34.48% |
| 4+ chunks | recall@1 | 2 | 8 | 25.00% |
| 4+ chunks | recall@2 | 3 | 8 | 37.50% |
| 4+ chunks | recall@3 | 5 | 8 | 62.50% |
| 4+ chunks | recall@4 | 5 | 8 | 62.50% |
| 4+ chunks | recall@5 | 5 | 8 | 62.50% |
| 4+ chunks | MRR | 3.1987 | 8 | 39.98% |

## Embedding Evaluation: `mistral-embed-2312`

### Scope

- Model: `mistral-embed-2312`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1077
- Translation chunks: 1162
- Multi-chunk transcriptions: 21
- Multi-chunk translations: 133
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 490 | 995 | 49.25% |
| recall@2 | 576 | 995 | 57.89% |
| recall@3 | 623 | 995 | 62.61% |
| recall@4 | 646 | 995 | 64.92% |
| recall@5 | 665 | 995 | 66.83% |
| MRR | 572.6835 | 995 | 57.56% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 1 | 18 | 5.56% |
| coptic | recall@2 | 2 | 18 | 11.11% |
| coptic | recall@3 | 2 | 18 | 11.11% |
| coptic | recall@4 | 2 | 18 | 11.11% |
| coptic | recall@5 | 2 | 18 | 11.11% |
| coptic | MRR | 1.5468 | 18 | 8.59% |
| greek | recall@1 | 485 | 971 | 49.95% |
| greek | recall@2 | 569 | 971 | 58.60% |
| greek | recall@3 | 616 | 971 | 63.44% |
| greek | recall@4 | 639 | 971 | 65.81% |
| greek | recall@5 | 658 | 971 | 67.77% |
| greek | MRR | 566.6174 | 971 | 58.35% |
| latin | recall@1 | 2 | 4 | 50.00% |
| latin | recall@2 | 3 | 4 | 75.00% |
| latin | recall@3 | 3 | 4 | 75.00% |
| latin | recall@4 | 3 | 4 | 75.00% |
| latin | recall@5 | 3 | 4 | 75.00% |
| latin | MRR | 2.5192 | 4 | 62.98% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 480 | 974 | 49.28% |
| 1 chunk | recall@2 | 564 | 974 | 57.91% |
| 1 chunk | recall@3 | 610 | 974 | 62.63% |
| 1 chunk | recall@4 | 632 | 974 | 64.89% |
| 1 chunk | recall@5 | 651 | 974 | 66.84% |
| 1 chunk | MRR | 560.7497 | 974 | 57.57% |
| 2-3 chunks | recall@1 | 8 | 14 | 57.14% |
| 2-3 chunks | recall@2 | 8 | 14 | 57.14% |
| 2-3 chunks | recall@3 | 8 | 14 | 57.14% |
| 2-3 chunks | recall@4 | 9 | 14 | 64.29% |
| 2-3 chunks | recall@5 | 9 | 14 | 64.29% |
| 2-3 chunks | MRR | 8.4230 | 14 | 60.16% |
| 4+ chunks | recall@1 | 2 | 7 | 28.57% |
| 4+ chunks | recall@2 | 4 | 7 | 57.14% |
| 4+ chunks | recall@3 | 5 | 7 | 71.43% |
| 4+ chunks | recall@4 | 5 | 7 | 71.43% |
| 4+ chunks | recall@5 | 5 | 7 | 71.43% |
| 4+ chunks | MRR | 3.5108 | 7 | 50.15% |

## Embedding Evaluation: `Qwen/Qwen3-Embedding-0.6B`

### Scope

- Model: `Qwen/Qwen3-Embedding-0.6B`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1077
- Translation chunks: 1162
- Multi-chunk transcriptions: 21
- Multi-chunk translations: 133
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 706 | 995 | 70.95% |
| recall@2 | 778 | 995 | 78.19% |
| recall@3 | 805 | 995 | 80.90% |
| recall@4 | 826 | 995 | 83.02% |
| recall@5 | 840 | 995 | 84.42% |
| MRR | 767.0104 | 995 | 77.09% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 3 | 18 | 16.67% |
| coptic | recall@2 | 3 | 18 | 16.67% |
| coptic | recall@3 | 3 | 18 | 16.67% |
| coptic | recall@4 | 3 | 18 | 16.67% |
| coptic | recall@5 | 3 | 18 | 16.67% |
| coptic | MRR | 3.3809 | 18 | 18.78% |
| greek | recall@1 | 698 | 971 | 71.88% |
| greek | recall@2 | 770 | 971 | 79.30% |
| greek | recall@3 | 796 | 971 | 81.98% |
| greek | recall@4 | 817 | 971 | 84.14% |
| greek | recall@5 | 831 | 971 | 85.58% |
| greek | MRR | 758.2961 | 971 | 78.09% |
| latin | recall@1 | 3 | 4 | 75.00% |
| latin | recall@2 | 3 | 4 | 75.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 3.3333 | 4 | 83.33% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 697 | 974 | 71.56% |
| 1 chunk | recall@2 | 766 | 974 | 78.64% |
| 1 chunk | recall@3 | 790 | 974 | 81.11% |
| 1 chunk | recall@4 | 811 | 974 | 83.26% |
| 1 chunk | recall@5 | 825 | 974 | 84.70% |
| 1 chunk | MRR | 755.1798 | 974 | 77.53% |
| 2-3 chunks | recall@1 | 6 | 14 | 42.86% |
| 2-3 chunks | recall@2 | 9 | 14 | 64.29% |
| 2-3 chunks | recall@3 | 11 | 14 | 78.57% |
| 2-3 chunks | recall@4 | 11 | 14 | 78.57% |
| 2-3 chunks | recall@5 | 11 | 14 | 78.57% |
| 2-3 chunks | MRR | 8.4415 | 14 | 60.30% |
| 4+ chunks | recall@1 | 3 | 7 | 42.86% |
| 4+ chunks | recall@2 | 3 | 7 | 42.86% |
| 4+ chunks | recall@3 | 4 | 7 | 57.14% |
| 4+ chunks | recall@4 | 4 | 7 | 57.14% |
| 4+ chunks | recall@5 | 4 | 7 | 57.14% |
| 4+ chunks | MRR | 3.3891 | 7 | 48.42% |

## Embedding Evaluation: `Qwen/Qwen3-Embedding-4B`

### Scope

- Model: `Qwen/Qwen3-Embedding-4B`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1077
- Translation chunks: 1162
- Multi-chunk transcriptions: 21
- Multi-chunk translations: 133
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 899 | 995 | 90.35% |
| recall@2 | 926 | 995 | 93.07% |
| recall@3 | 933 | 995 | 93.77% |
| recall@4 | 941 | 995 | 94.57% |
| recall@5 | 946 | 995 | 95.08% |
| MRR | 919.9352 | 995 | 92.46% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 2 | 18 | 11.11% |
| coptic | recall@2 | 4 | 18 | 22.22% |
| coptic | recall@3 | 4 | 18 | 22.22% |
| coptic | recall@4 | 4 | 18 | 22.22% |
| coptic | recall@5 | 4 | 18 | 22.22% |
| coptic | MRR | 3.0900 | 18 | 17.17% |
| greek | recall@1 | 891 | 971 | 91.76% |
| greek | recall@2 | 916 | 971 | 94.34% |
| greek | recall@3 | 923 | 971 | 95.06% |
| greek | recall@4 | 931 | 971 | 95.88% |
| greek | recall@5 | 936 | 971 | 96.40% |
| greek | MRR | 910.8452 | 971 | 93.80% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 883 | 974 | 90.66% |
| 1 chunk | recall@2 | 906 | 974 | 93.02% |
| 1 chunk | recall@3 | 912 | 974 | 93.63% |
| 1 chunk | recall@4 | 920 | 974 | 94.46% |
| 1 chunk | recall@5 | 925 | 974 | 94.97% |
| 1 chunk | MRR | 901.6019 | 974 | 92.57% |
| 2-3 chunks | recall@1 | 12 | 14 | 85.71% |
| 2-3 chunks | recall@2 | 14 | 14 | 100.00% |
| 2-3 chunks | recall@3 | 14 | 14 | 100.00% |
| 2-3 chunks | recall@4 | 14 | 14 | 100.00% |
| 2-3 chunks | recall@5 | 14 | 14 | 100.00% |
| 2-3 chunks | MRR | 13.0000 | 14 | 92.86% |
| 4+ chunks | recall@1 | 4 | 7 | 57.14% |
| 4+ chunks | recall@2 | 6 | 7 | 85.71% |
| 4+ chunks | recall@3 | 7 | 7 | 100.00% |
| 4+ chunks | recall@4 | 7 | 7 | 100.00% |
| 4+ chunks | recall@5 | 7 | 7 | 100.00% |
| 4+ chunks | MRR | 5.3333 | 7 | 76.19% |

## Embedding Evaluation: `Qwen/Qwen3-Embedding-8B`

### Scope

- Model: `Qwen/Qwen3-Embedding-8B`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1077
- Translation chunks: 1162
- Multi-chunk transcriptions: 21
- Multi-chunk translations: 133
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 932 | 995 | 93.67% |
| recall@2 | 961 | 995 | 96.58% |
| recall@3 | 969 | 995 | 97.39% |
| recall@4 | 972 | 995 | 97.69% |
| recall@5 | 974 | 995 | 97.89% |
| MRR | 950.8077 | 995 | 95.56% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 5 | 18 | 27.78% |
| coptic | recall@2 | 6 | 18 | 33.33% |
| coptic | recall@3 | 6 | 18 | 33.33% |
| coptic | recall@4 | 7 | 18 | 38.89% |
| coptic | recall@5 | 7 | 18 | 38.89% |
| coptic | MRR | 5.9098 | 18 | 32.83% |
| greek | recall@1 | 921 | 971 | 94.85% |
| greek | recall@2 | 949 | 971 | 97.73% |
| greek | recall@3 | 957 | 971 | 98.56% |
| greek | recall@4 | 959 | 971 | 98.76% |
| greek | recall@5 | 961 | 971 | 98.97% |
| greek | MRR | 938.8979 | 971 | 96.69% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 912 | 974 | 93.63% |
| 1 chunk | recall@2 | 940 | 974 | 96.51% |
| 1 chunk | recall@3 | 948 | 974 | 97.33% |
| 1 chunk | recall@4 | 951 | 974 | 97.64% |
| 1 chunk | recall@5 | 953 | 974 | 97.84% |
| 1 chunk | MRR | 930.3077 | 974 | 95.51% |
| 2-3 chunks | recall@1 | 13 | 14 | 92.86% |
| 2-3 chunks | recall@2 | 14 | 14 | 100.00% |
| 2-3 chunks | recall@3 | 14 | 14 | 100.00% |
| 2-3 chunks | recall@4 | 14 | 14 | 100.00% |
| 2-3 chunks | recall@5 | 14 | 14 | 100.00% |
| 2-3 chunks | MRR | 13.5000 | 14 | 96.43% |
| 4+ chunks | recall@1 | 7 | 7 | 100.00% |
| 4+ chunks | recall@2 | 7 | 7 | 100.00% |
| 4+ chunks | recall@3 | 7 | 7 | 100.00% |
| 4+ chunks | recall@4 | 7 | 7 | 100.00% |
| 4+ chunks | recall@5 | 7 | 7 | 100.00% |
| 4+ chunks | MRR | 7.0000 | 7 | 100.00% |

## Embedding Evaluation: `text-embedding-3-large`

### Scope

- Model: `text-embedding-3-large`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 814 | 995 | 81.81% |
| recall@2 | 877 | 995 | 88.14% |
| recall@3 | 902 | 995 | 90.65% |
| recall@4 | 923 | 995 | 92.76% |
| recall@5 | 929 | 995 | 93.37% |
| MRR | 864.4766 | 995 | 86.88% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 2 | 18 | 11.11% |
| coptic | recall@2 | 4 | 18 | 22.22% |
| coptic | recall@3 | 4 | 18 | 22.22% |
| coptic | recall@4 | 4 | 18 | 22.22% |
| coptic | recall@5 | 5 | 18 | 27.78% |
| coptic | MRR | 3.5539 | 18 | 19.74% |
| greek | recall@1 | 806 | 971 | 83.01% |
| greek | recall@2 | 867 | 971 | 89.29% |
| greek | recall@3 | 892 | 971 | 91.86% |
| greek | recall@4 | 913 | 971 | 94.03% |
| greek | recall@5 | 918 | 971 | 94.54% |
| greek | MRR | 854.9227 | 971 | 88.05% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 793 | 966 | 82.09% |
| 1 chunk | recall@2 | 854 | 966 | 88.41% |
| 1 chunk | recall@3 | 879 | 966 | 90.99% |
| 1 chunk | recall@4 | 898 | 966 | 92.96% |
| 1 chunk | recall@5 | 903 | 966 | 93.48% |
| 1 chunk | MRR | 841.5620 | 966 | 87.12% |
| 2-3 chunks | recall@1 | 15 | 21 | 71.43% |
| 2-3 chunks | recall@2 | 16 | 21 | 76.19% |
| 2-3 chunks | recall@3 | 16 | 21 | 76.19% |
| 2-3 chunks | recall@4 | 18 | 21 | 85.71% |
| 2-3 chunks | recall@5 | 19 | 21 | 90.48% |
| 2-3 chunks | MRR | 16.4024 | 21 | 78.11% |
| 4+ chunks | recall@1 | 6 | 8 | 75.00% |
| 4+ chunks | recall@2 | 7 | 8 | 87.50% |
| 4+ chunks | recall@3 | 7 | 8 | 87.50% |
| 4+ chunks | recall@4 | 7 | 8 | 87.50% |
| 4+ chunks | recall@5 | 7 | 8 | 87.50% |
| 4+ chunks | MRR | 6.5122 | 8 | 81.40% |

## Embedding Evaluation: `text-embedding-3-small`

### Scope

- Model: `text-embedding-3-small`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 246 | 995 | 24.72% |
| recall@2 | 344 | 995 | 34.57% |
| recall@3 | 382 | 995 | 38.39% |
| recall@4 | 418 | 995 | 42.01% |
| recall@5 | 448 | 995 | 45.03% |
| MRR | 346.0606 | 995 | 34.78% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 1 | 18 | 5.56% |
| coptic | recall@2 | 1 | 18 | 5.56% |
| coptic | recall@3 | 1 | 18 | 5.56% |
| coptic | recall@4 | 1 | 18 | 5.56% |
| coptic | recall@5 | 1 | 18 | 5.56% |
| coptic | MRR | 1.0456 | 18 | 5.81% |
| greek | recall@1 | 239 | 971 | 24.61% |
| greek | recall@2 | 337 | 971 | 34.71% |
| greek | recall@3 | 375 | 971 | 38.62% |
| greek | recall@4 | 411 | 971 | 42.33% |
| greek | recall@5 | 441 | 971 | 45.42% |
| greek | MRR | 339.0149 | 971 | 34.91% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 237 | 966 | 24.53% |
| 1 chunk | recall@2 | 334 | 966 | 34.58% |
| 1 chunk | recall@3 | 370 | 966 | 38.30% |
| 1 chunk | recall@4 | 406 | 966 | 42.03% |
| 1 chunk | recall@5 | 436 | 966 | 45.13% |
| 1 chunk | MRR | 335.0417 | 966 | 34.68% |
| 2-3 chunks | recall@1 | 8 | 21 | 38.10% |
| 2-3 chunks | recall@2 | 9 | 21 | 42.86% |
| 2-3 chunks | recall@3 | 11 | 21 | 52.38% |
| 2-3 chunks | recall@4 | 11 | 21 | 52.38% |
| 2-3 chunks | recall@5 | 11 | 21 | 52.38% |
| 2-3 chunks | MRR | 9.6635 | 21 | 46.02% |
| 4+ chunks | recall@1 | 1 | 8 | 12.50% |
| 4+ chunks | recall@2 | 1 | 8 | 12.50% |
| 4+ chunks | recall@3 | 1 | 8 | 12.50% |
| 4+ chunks | recall@4 | 1 | 8 | 12.50% |
| 4+ chunks | recall@5 | 1 | 8 | 12.50% |
| 4+ chunks | MRR | 1.3554 | 8 | 16.94% |

## Embedding Evaluation: `text-embedding-ada-002`

### Scope

- Model: `text-embedding-ada-002`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 320 | 995 | 32.16% |
| recall@2 | 390 | 995 | 39.20% |
| recall@3 | 443 | 995 | 44.52% |
| recall@4 | 478 | 995 | 48.04% |
| recall@5 | 502 | 995 | 50.45% |
| MRR | 408.5842 | 995 | 41.06% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 1 | 2 | 50.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 1.5000 | 2 | 75.00% |
| coptic | recall@1 | 1 | 18 | 5.56% |
| coptic | recall@2 | 1 | 18 | 5.56% |
| coptic | recall@3 | 2 | 18 | 11.11% |
| coptic | recall@4 | 2 | 18 | 11.11% |
| coptic | recall@5 | 2 | 18 | 11.11% |
| coptic | MRR | 1.4020 | 18 | 7.79% |
| greek | recall@1 | 316 | 971 | 32.54% |
| greek | recall@2 | 384 | 971 | 39.55% |
| greek | recall@3 | 436 | 971 | 44.90% |
| greek | recall@4 | 471 | 971 | 48.51% |
| greek | recall@5 | 495 | 971 | 50.98% |
| greek | MRR | 403.1322 | 971 | 41.52% |
| latin | recall@1 | 2 | 4 | 50.00% |
| latin | recall@2 | 3 | 4 | 75.00% |
| latin | recall@3 | 3 | 4 | 75.00% |
| latin | recall@4 | 3 | 4 | 75.00% |
| latin | recall@5 | 3 | 4 | 75.00% |
| latin | MRR | 2.5500 | 4 | 63.75% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 310 | 966 | 32.09% |
| 1 chunk | recall@2 | 378 | 966 | 39.13% |
| 1 chunk | recall@3 | 430 | 966 | 44.51% |
| 1 chunk | recall@4 | 465 | 966 | 48.14% |
| 1 chunk | recall@5 | 489 | 966 | 50.62% |
| 1 chunk | MRR | 396.8441 | 966 | 41.08% |
| 2-3 chunks | recall@1 | 7 | 21 | 33.33% |
| 2-3 chunks | recall@2 | 8 | 21 | 38.10% |
| 2-3 chunks | recall@3 | 9 | 21 | 42.86% |
| 2-3 chunks | recall@4 | 9 | 21 | 42.86% |
| 2-3 chunks | recall@5 | 9 | 21 | 42.86% |
| 2-3 chunks | MRR | 8.1954 | 21 | 39.03% |
| 4+ chunks | recall@1 | 3 | 8 | 37.50% |
| 4+ chunks | recall@2 | 4 | 8 | 50.00% |
| 4+ chunks | recall@3 | 4 | 8 | 50.00% |
| 4+ chunks | recall@4 | 4 | 8 | 50.00% |
| 4+ chunks | recall@5 | 4 | 8 | 50.00% |
| 4+ chunks | MRR | 3.5447 | 8 | 44.31% |

## Embedding Evaluation: `voyage-4`

### Scope

- Model: `voyage-4`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 893 | 995 | 89.75% |
| recall@2 | 926 | 995 | 93.07% |
| recall@3 | 940 | 995 | 94.47% |
| recall@4 | 941 | 995 | 94.57% |
| recall@5 | 948 | 995 | 95.28% |
| MRR | 918.3416 | 995 | 92.30% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 6 | 18 | 33.33% |
| coptic | recall@2 | 6 | 18 | 33.33% |
| coptic | recall@3 | 7 | 18 | 38.89% |
| coptic | recall@4 | 7 | 18 | 38.89% |
| coptic | recall@5 | 8 | 18 | 44.44% |
| coptic | MRR | 6.8084 | 18 | 37.82% |
| greek | recall@1 | 881 | 971 | 90.73% |
| greek | recall@2 | 914 | 971 | 94.13% |
| greek | recall@3 | 927 | 971 | 95.47% |
| greek | recall@4 | 928 | 971 | 95.57% |
| greek | recall@5 | 934 | 971 | 96.19% |
| greek | MRR | 905.5332 | 971 | 93.26% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 869 | 966 | 89.96% |
| 1 chunk | recall@2 | 901 | 966 | 93.27% |
| 1 chunk | recall@3 | 915 | 966 | 94.72% |
| 1 chunk | recall@4 | 916 | 966 | 94.82% |
| 1 chunk | recall@5 | 921 | 966 | 95.34% |
| 1 chunk | MRR | 893.2606 | 966 | 92.47% |
| 2-3 chunks | recall@1 | 19 | 21 | 90.48% |
| 2-3 chunks | recall@2 | 19 | 21 | 90.48% |
| 2-3 chunks | recall@3 | 19 | 21 | 90.48% |
| 2-3 chunks | recall@4 | 19 | 21 | 90.48% |
| 2-3 chunks | recall@5 | 20 | 21 | 95.24% |
| 2-3 chunks | MRR | 19.2143 | 21 | 91.50% |
| 4+ chunks | recall@1 | 5 | 8 | 62.50% |
| 4+ chunks | recall@2 | 6 | 8 | 75.00% |
| 4+ chunks | recall@3 | 6 | 8 | 75.00% |
| 4+ chunks | recall@4 | 6 | 8 | 75.00% |
| 4+ chunks | recall@5 | 7 | 8 | 87.50% |
| 4+ chunks | MRR | 5.8667 | 8 | 73.33% |

## Embedding Evaluation: `voyage-4-large`

### Scope

- Model: `voyage-4-large`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 929 | 995 | 93.37% |
| recall@2 | 956 | 995 | 96.08% |
| recall@3 | 963 | 995 | 96.78% |
| recall@4 | 969 | 995 | 97.39% |
| recall@5 | 969 | 995 | 97.39% |
| MRR | 948.1399 | 995 | 95.29% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 8 | 18 | 44.44% |
| coptic | recall@2 | 11 | 18 | 61.11% |
| coptic | recall@3 | 11 | 18 | 61.11% |
| coptic | recall@4 | 11 | 18 | 61.11% |
| coptic | recall@5 | 11 | 18 | 61.11% |
| coptic | MRR | 9.7871 | 18 | 54.37% |
| greek | recall@1 | 915 | 971 | 94.23% |
| greek | recall@2 | 939 | 971 | 96.70% |
| greek | recall@3 | 946 | 971 | 97.43% |
| greek | recall@4 | 952 | 971 | 98.04% |
| greek | recall@5 | 952 | 971 | 98.04% |
| greek | MRR | 932.3528 | 971 | 96.02% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 905 | 966 | 93.69% |
| 1 chunk | recall@2 | 930 | 966 | 96.27% |
| 1 chunk | recall@3 | 936 | 966 | 96.89% |
| 1 chunk | recall@4 | 941 | 966 | 97.41% |
| 1 chunk | recall@5 | 941 | 966 | 97.41% |
| 1 chunk | MRR | 922.5387 | 966 | 95.50% |
| 2-3 chunks | recall@1 | 19 | 21 | 90.48% |
| 2-3 chunks | recall@2 | 20 | 21 | 95.24% |
| 2-3 chunks | recall@3 | 21 | 21 | 100.00% |
| 2-3 chunks | recall@4 | 21 | 21 | 100.00% |
| 2-3 chunks | recall@5 | 21 | 21 | 100.00% |
| 2-3 chunks | MRR | 19.8333 | 21 | 94.44% |
| 4+ chunks | recall@1 | 5 | 8 | 62.50% |
| 4+ chunks | recall@2 | 6 | 8 | 75.00% |
| 4+ chunks | recall@3 | 6 | 8 | 75.00% |
| 4+ chunks | recall@4 | 7 | 8 | 87.50% |
| 4+ chunks | recall@5 | 7 | 8 | 87.50% |
| 4+ chunks | MRR | 5.7679 | 8 | 72.10% |

## Embedding Evaluation: `voyage-4-lite`

### Scope

- Model: `voyage-4-lite`
- Transcription documents: 996
- Translation documents: 999
- Transcription chunks: 1087
- Translation chunks: 1185
- Multi-chunk transcriptions: 29
- Multi-chunk translations: 154
- Paired documents evaluated: 995
- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).

### Metrics

| Metric | Total | Queries | Score |
| --- | ---: | ---: | ---: |
| recall@1 | 804 | 995 | 80.80% |
| recall@2 | 846 | 995 | 85.03% |
| recall@3 | 866 | 995 | 87.04% |
| recall@4 | 887 | 995 | 89.15% |
| recall@5 | 895 | 995 | 89.95% |
| MRR | 844.0886 | 995 | 84.83% |

### Metrics by Language

| Language | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| arabic | recall@1 | 2 | 2 | 100.00% |
| arabic | recall@2 | 2 | 2 | 100.00% |
| arabic | recall@3 | 2 | 2 | 100.00% |
| arabic | recall@4 | 2 | 2 | 100.00% |
| arabic | recall@5 | 2 | 2 | 100.00% |
| arabic | MRR | 2.0000 | 2 | 100.00% |
| coptic | recall@1 | 1 | 18 | 5.56% |
| coptic | recall@2 | 1 | 18 | 5.56% |
| coptic | recall@3 | 1 | 18 | 5.56% |
| coptic | recall@4 | 1 | 18 | 5.56% |
| coptic | recall@5 | 1 | 18 | 5.56% |
| coptic | MRR | 1.1702 | 18 | 6.50% |
| greek | recall@1 | 797 | 971 | 82.08% |
| greek | recall@2 | 839 | 971 | 86.41% |
| greek | recall@3 | 859 | 971 | 88.47% |
| greek | recall@4 | 880 | 971 | 90.63% |
| greek | recall@5 | 888 | 971 | 91.45% |
| greek | MRR | 836.9184 | 971 | 86.19% |
| latin | recall@1 | 4 | 4 | 100.00% |
| latin | recall@2 | 4 | 4 | 100.00% |
| latin | recall@3 | 4 | 4 | 100.00% |
| latin | recall@4 | 4 | 4 | 100.00% |
| latin | recall@5 | 4 | 4 | 100.00% |
| latin | MRR | 4.0000 | 4 | 100.00% |

### Metrics by Transcription Chunk Count

| Chunk group | Metric | Total | Queries | Score |
| --- | --- | ---: | ---: | ---: |
| 1 chunk | recall@1 | 782 | 966 | 80.95% |
| 1 chunk | recall@2 | 824 | 966 | 85.30% |
| 1 chunk | recall@3 | 844 | 966 | 87.37% |
| 1 chunk | recall@4 | 864 | 966 | 89.44% |
| 1 chunk | recall@5 | 871 | 966 | 90.17% |
| 1 chunk | MRR | 821.3708 | 966 | 85.03% |
| 2-3 chunks | recall@1 | 17 | 21 | 80.95% |
| 2-3 chunks | recall@2 | 17 | 21 | 80.95% |
| 2-3 chunks | recall@3 | 17 | 21 | 80.95% |
| 2-3 chunks | recall@4 | 17 | 21 | 80.95% |
| 2-3 chunks | recall@5 | 18 | 21 | 85.71% |
| 2-3 chunks | MRR | 17.3631 | 21 | 82.68% |
| 4+ chunks | recall@1 | 5 | 8 | 62.50% |
| 4+ chunks | recall@2 | 5 | 8 | 62.50% |
| 4+ chunks | recall@3 | 5 | 8 | 62.50% |
| 4+ chunks | recall@4 | 6 | 8 | 75.00% |
| 4+ chunks | recall@5 | 6 | 8 | 75.00% |
| 4+ chunks | MRR | 5.3548 | 8 | 66.93% |
