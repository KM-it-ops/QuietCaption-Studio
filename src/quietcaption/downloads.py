from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.request import Request, urlopen


def verify_sha256(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected.lower()


class VerifiedDownloader:
    def download(self, url: str, destination: Path, sha256: str, progress=None) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "QuietCaption-Studio/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with urlopen(Request(url, headers=headers), timeout=30) as response, partial.open("ab" if offset else "wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                if progress:
                    progress(output.tell())
        if not verify_sha256(partial, sha256):
            partial.unlink(missing_ok=True)
            raise ValueError("Downloaded model failed SHA-256 verification")
        os.replace(partial, destination)
        return destination

