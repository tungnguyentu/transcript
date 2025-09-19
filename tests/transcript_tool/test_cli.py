import textwrap

from transcript_tool.cli import format_timestamp, segments_to_srt


def test_format_timestamp_zero():
    assert format_timestamp(0.0) == "00:00:00,000"


def test_format_timestamp_rounding():
    # 1.2345 seconds should round to 1.235 in milliseconds
    assert format_timestamp(1.2345) == "00:00:01,235"


def test_segments_to_srt_basic():
    segments = [
        {"start": 0.0, "end": 1.5, "text": "Hello"},
        {"start": 2.0, "end": 4.0, "text": "World"},
    ]
    expected = textwrap.dedent(
        """
        1
        00:00:00,000 --> 00:00:01,500
        Hello

        2
        00:00:02,000 --> 00:00:04,000
        World
        """
    ).lstrip() + "\n"
    assert segments_to_srt(segments) == expected


def test_segments_to_srt_ignores_empty_text():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "  "},
        {"start": 1.0, "end": 2.0, "text": "Next"},
    ]
    expected = textwrap.dedent(
        """
        1
        00:00:01,000 --> 00:00:02,000
        Next
        """
    ).lstrip() + "\n"
    assert segments_to_srt(segments) == expected


def test_segments_to_srt_returns_empty_string_when_no_segments():
    assert segments_to_srt([]) == ""
