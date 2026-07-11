"""PyInstaller launcher that preserves QuietCaption's package imports."""

from quietcaption.app import main


if __name__ == "__main__":
    raise SystemExit(main())

