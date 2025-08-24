"""Summarization logic with abstractive (HF) and extractive fallback (sumy)."""

import os
import re
import math
from typing import Tuple

HAS_TRANSFORMERS = False
try:
    from transformers import pipeline
    import torch
    HAS_TRANSFORMERS = True
except Exception:
    HAS_TRANSFORMERS = False

HAS_SUMY = False
try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.text_rank import TextRankSummarizer
    HAS_SUMY = True
except Exception:
    HAS_SUMY = False

DEFAULT_MODEL = os.getenv("SUMMARIZER_MODEL", "sshleifer/distilbart-cnn-12-6")

_hf_summarizer = None

def _init_hf():
    global _hf_summarizer
    if _hf_summarizer is not None:
        return
    if not HAS_TRANSFORMERS:
        return
    try:
        device = 0 if torch.cuda.is_available() else -1
        _hf_summarizer = pipeline("summarization", model=DEFAULT_MODEL, device=device)
    except Exception:
        _hf_summarizer = None

def _chunk_by_words(text: str, max_words: int = 700):
    words = text.split()
    if len(words) <= max_words:
        return [text]
    chunks = []
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i : i + max_words])
        chunks.append(chunk)
    return chunks

def _extractive_summary(text: str, ratio: float = 0.2) -> str:
    text = text.strip()
    if not text:
        return ""
    if not HAS_SUMY:
        sents = re.split(r'(?<=[\.\?\!])\s+', text)
        n = max(1, int(len(sents) * ratio))
        return " ".join(sents[:n]).strip()
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        sents = re.split(r'(?<=[\.\?\!])\s+', text)
        n = max(1, int(len(sents) * ratio))
        tr = TextRankSummarizer()
        summary_sentences = tr(parser.document, n)
        return " ".join(str(s) for s in summary_sentences).strip()
    except Exception:
        sents = re.split(r'(?<=[\.\?\!])\s+', text)
        n = max(1, int(len(sents) * ratio))
        return " ".join(sents[:n]).strip()

def _abstractive_summary(text: str, ratio: float = 0.2) -> str:
    _init_hf()
    if not _hf_summarizer:
        return _extractive_summary(text, ratio=ratio)

    # chunk input into manageable pieces
    chunks = _chunk_by_words(text, max_words=700)
    summaries = []
    for chunk in chunks:
        try:
            # approximate target lengths by words -> tokens; keep safe bounds
            max_len = min(512, max(50, int(len(chunk.split()) * ratio) + 30))
            res = _hf_summarizer(chunk, max_length=max_len, min_length=20, do_sample=False)
            summaries.append(res[0]["summary_text"].strip())
        except Exception:
            summaries.append(_extractive_summary(chunk, ratio=min(0.25, ratio)))

    if len(summaries) == 1:
        return summaries[0]
    combined = " ".join(summaries)
    # final distillation
    try:
        max_len = min(512, max(50, int(len(combined.split()) * ratio)))
        res = _hf_summarizer(combined, max_length=max_len, min_length=20, do_sample=False)
        return res[0]["summary_text"].strip()
    except Exception:
        return combined

def summarize_text(text: str, method: str = "auto", ratio: float = 0.2) -> Tuple[str, dict]:
    text = text.strip()
    if not text:
        return "", {"method": method, "reason": "empty input"}

    chosen = method
    if method == "auto":
        chosen = "abstractive" if HAS_TRANSFORMERS else "extractive"

    meta = {"requested_method": method, "chosen_method": chosen}

    if chosen == "abstractive":
        summary = _abstractive_summary(text, ratio=ratio)
    else:
        summary = _extractive_summary(text, ratio=ratio)

    meta["length_input_chars"] = len(text)
    meta["length_summary_chars"] = len(summary)
    return summary, meta
