from pathlib import Path

from .domain import SubtitleSegment


class DemoMedia:
    def probe(self, path):
        return type("MediaInfo", (), {"duration": 8.0})()

    def extract_audio(self, source, destination, cancel=None):
        if cancel and cancel.cancelled:
            raise InterruptedError("Job cancelled")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"quietcaption-demo-audio")
        return destination


class DemoTranscriber:
    def transcribe(self, path, language="auto", progress=None, cancel=None):
        if cancel and cancel.cancelled:
            raise InterruptedError("Job cancelled")
        segments = [
            SubtitleSegment("demo-1", 0.0, 3.2, "Welcome to QuietCaption Studio."),
            SubtitleSegment("demo-2", 3.4, 7.5, "Your media and words stay on this computer."),
        ]
        if progress:
            progress(7.5)
        return "en", segments


class DemoTranslator:
    TRANSLATIONS = {
        "es": ["Bienvenido a QuietCaption Studio.", "Tus archivos y palabras permanecen en esta computadora."],
        "fr": ["Bienvenue dans QuietCaption Studio.", "Vos fichiers et vos mots restent sur cet ordinateur."],
        "de": ["Willkommen bei QuietCaption Studio.", "Ihre Medien und Wörter bleiben auf diesem Computer."],
    }

    def translate(self, texts, source_language, target_language):
        target_language = {"spa_Latn": "es", "fra_Latn": "fr", "deu_Latn": "de"}.get(target_language, target_language)
        if target_language not in self.TRANSLATIONS:
            raise ValueError(f"The demo has no {target_language} translation model")
        return self.TRANSLATIONS[target_language]
