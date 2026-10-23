# RAGOps Evaluation Guide

Retrieval relevance combines reference-context token F1 with an exact expected-source match. This measures explainable lexical and document-level coverage, not semantic understanding.

Faithfulness splits an answer into sentences and checks token F1 support against retrieved context. A claim with support of at least 0.5 is treated as supported. This is a heuristic and not semantic entailment.

Answer correctness uses token F1 between the generated answer and expected answer. It measures deterministic fact-token coverage and is not a human or model judge.

Citation accuracy checks that the expected source identifier appears in the generated citations. Missing, invalid, and unsupported citations must remain visible in case results.

Unavailable provider metrics remain null. A threshold requiring an unavailable metric fails rather than treating the metric as zero or passing the run.
