from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .languages import resolve_nllb_code


class Translator(Protocol):
    def translate(self, texts: list[str], source_language: str, target_language: str, cancel=None) -> list[str]: ...


def _check_cancel(cancel) -> None:
    if cancel is not None and cancel.cancelled:
        raise InterruptedError("Translation cancelled")


class IdentityTranslator:
    def translate(self, texts: list[str], source_language: str, target_language: str, cancel=None) -> list[str]:
        _check_cancel(cancel)
        if source_language != target_language:
            raise ValueError("No offline translation model is configured for this language pair")
        return list(texts)


class CTranslate2Translator:
    def __init__(self, model_path: Path, source_token: str | None = None, target_token: str | None = None):
        self.model_path, self.source_token, self.target_token = model_path, source_token, target_token

    def translate(self, texts: list[str], source_language: str, target_language: str, cancel=None) -> list[str]:
        _check_cancel(cancel)
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("Install the inference extra to use offline translation") from exc
        tokenizer = spm.SentencePieceProcessor(model_file=str(self.model_path / "sentencepiece.model"))
        translator = ctranslate2.Translator(str(self.model_path), device="auto")
        batches = []
        for text in texts:
            _check_cancel(cancel)
            tokens = tokenizer.encode(text, out_type=str)
            if self.source_token:
                tokens.insert(0, self.source_token.format(lang=source_language))
            batches.append(tokens)
        prefix = [[self.target_token.format(lang=target_language)]] * len(batches) if self.target_token else None
        results = translator.translate_batch(batches, target_prefix=prefix)
        _check_cancel(cancel)
        return [tokenizer.decode(item.hypotheses[0]) for item in results]


class NllbCTranslate2Translator:
    """Offline NLLB inference using an installed CTranslate2 snapshot."""

    def __init__(self, model_path: Path, device: str = "cpu", engine=None, tokenizer=None, *, compute_type: str | None = None):
        self.model_path = Path(model_path)
        self.device = "cuda" if device == "cuda" else "cpu"
        self.compute_type = compute_type or ("int8_float16" if self.device == "cuda" else "int8")
        self._engine = engine
        self._tokenizer = tokenizer

    def _load(self) -> None:
        if self._engine is not None and self._tokenizer is not None:
            return
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("Install the inference extra to use NLLB offline translation") from exc
        tokenizer_path = self.model_path / "sentencepiece.bpe.model"
        if not tokenizer_path.is_file():
            raise RuntimeError("The active translation model is missing sentencepiece.bpe.model; verify or repair it")
        self._tokenizer = spm.SentencePieceProcessor(model_file=str(tokenizer_path))
        self._engine = ctranslate2.Translator(str(self.model_path), device=self.device, compute_type=self.compute_type)

    def translate(self, texts: list[str], source_language: str, target_language: str, cancel=None) -> list[str]:
        _check_cancel(cancel)
        self._load()
        source = resolve_nllb_code(source_language)
        target = resolve_nllb_code(target_language)
        translated = []
        for start in range(0, len(texts), 32):
            _check_cancel(cancel)
            batches = [
                [source, *self._tokenizer.encode(text, out_type=str), "</s>"]
                for text in texts[start:start + 32]
            ]
            results = self._engine.translate_batch(
                batches,
                target_prefix=[[target] for _ in batches],
                batch_type="tokens",
                max_batch_size=1024,
                beam_size=4,
            )
            _check_cancel(cancel)
            for item in results:
                tokens = list(item.hypotheses[0])
                if tokens and tokens[0] == target:
                    tokens.pop(0)
                if tokens and tokens[-1] == "</s>":
                    tokens.pop()
                translated.append(self._tokenizer.decode(tokens))
        return translated
