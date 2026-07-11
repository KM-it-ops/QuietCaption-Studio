from quietcaption.domain import Project, SubtitleSegment, SubtitleTrack


def test_segment_split_and_merge_preserve_timing_and_text():
    segment = SubtitleSegment(id="a", start=1.0, end=5.0, text="hello world")
    left, right = segment.split(2.5, 6)
    assert (left.start, left.end, left.text) == (1.0, 2.5, "hello")
    assert (right.start, right.end, right.text) == (2.5, 5.0, "world")
    assert left.merge(right).text == "hello world"


def test_track_reports_overlaps_and_project_round_trips():
    track = SubtitleTrack(language="en", segments=[
        SubtitleSegment(id="a", start=0, end=2, text="One"),
        SubtitleSegment(id="b", start=1.5, end=3, text="Two"),
    ])
    assert track.validate()[0].code == "overlap"
    project = Project.new("demo.mp4", track)
    assert Project.from_dict(project.to_dict()) == project

