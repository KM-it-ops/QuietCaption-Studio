import pytest

from quietcaption.translation import NllbCTranslate2Translator


class FakeSentencePiece:
    def encode(self, text, out_type=str):
        return text.split()

    def decode(self, tokens):
        return " ".join(tokens)


class FakeResult:
    def __init__(self, tokens):
        self.hypotheses = [tokens]


class FakeEngine:
    def __init__(self):
        self.calls = []

    def translate_batch(self, batches, **options):
        self.calls.append((batches, options))
        return [FakeResult(["spa_Latn", "hola"]) for _ in batches]


def test_nllb_ctranslate2_uses_local_language_tokens_and_strips_prefix(tmp_path):
    engine = FakeEngine()
    translator = NllbCTranslate2Translator(
        tmp_path,
        device="cpu",
        engine=engine,
        tokenizer=FakeSentencePiece(),
    )

    translated = translator.translate(["hello world"], "en", "es")

    assert translated == ["hola"]
    batches, options = engine.calls[0]
    assert batches == [["eng_Latn", "hello", "world", "</s>"]]
    assert options["target_prefix"] == [["spa_Latn"]]
    assert options["beam_size"] == 4


def test_nllb_translation_checks_cancellation_between_local_chunks(tmp_path):
    engine = FakeEngine()
    translator = NllbCTranslate2Translator(tmp_path, engine=engine, tokenizer=FakeSentencePiece())
    cancel = type("Token", (), {"cancelled": False})()

    def cancel_after_first_batch(batches, **options):
        cancel.cancelled = True
        return [FakeResult(["spa_Latn", "hola"]) for _ in batches]

    engine.translate_batch = cancel_after_first_batch

    with pytest.raises(InterruptedError, match="cancelled"):
        translator.translate(["one", "two"], "en", "es", cancel=cancel)
