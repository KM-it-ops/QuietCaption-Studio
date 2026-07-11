from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Translator(Protocol):
    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]: ...


class IdentityTranslator:
    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]:
        if source_language != target_language:
            raise ValueError("No offline translation model is configured for this language pair")
        return list(texts)


class CTranslate2Translator:
    def __init__(self, model_path: Path, source_token: str | None = None, target_token: str | None = None):
        self.model_path, self.source_token, self.target_token = model_path, source_token, target_token

    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]:
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("Install the inference extra to use offline translation") from exc
        tokenizer = spm.SentencePieceProcessor(model_file=str(self.model_path / "sentencepiece.model"))
        translator = ctranslate2.Translator(str(self.model_path), device="auto")
        batches = []
        for text in texts:
            tokens = tokenizer.encode(text, out_type=str)
            if self.source_token:
                tokens.insert(0, self.source_token.format(lang=source_language))
            batches.append(tokens)
        prefix = [[self.target_token.format(lang=target_language)]] * len(batches) if self.target_token else None
        results = translator.translate_batch(batches, target_prefix=prefix)
        return [tokenizer.decode(item.hypotheses[0]) for item in results]

