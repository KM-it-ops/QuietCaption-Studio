# Third-party notices

QuietCaption Studio can use the following separately distributed components. Their own licenses apply:

- PySide6 / Qt for Python — LGPLv3/GPLv3 or commercial terms.
- Faster-Whisper — MIT License.
- CTranslate2 — MIT License.
- SentencePiece — Apache License 2.0.
- PyAV — BSD 3-Clause License; its binary wheels include FFmpeg libraries under their applicable licenses.
- FFmpeg — LGPL/GPL depending on the selected build and codecs.
- Whisper and translation model weights — each model's published license.

The default broad translation catalog entry is an INT8 CTranslate2 conversion of Meta NLLB-200 Distilled 600M and retains the original CC-BY-NC-4.0 non-commercial license. It is downloaded separately only after the user reviews and accepts the model details.

The build does not bundle model weights. Before distributing an FFmpeg binary or model, include the exact notices and source/license offer required by that artifact.
