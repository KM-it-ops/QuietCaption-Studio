from quietcaption.domain import SubtitleSegment, SubtitleTrack
from quietcaption.formats import SrtWriter, TextWriter, VttWriter, format_timestamp


def test_timestamp_supports_more_than_24_hours():
    assert format_timestamp(90061.007, ",") == "25:01:01,007"


def test_writers_emit_unicode_and_expected_headers():
    track = SubtitleTrack("ar", [SubtitleSegment("a", 0.25, 2.0, "مرحبا")])
    assert "00:00:00,250 --> 00:00:02,000" in SrtWriter().render(track)
    assert VttWriter().render(track).startswith("WEBVTT\n\n")
    assert TextWriter().render(track) == "مرحبا\n"

