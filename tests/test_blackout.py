"""Unit tests for blacking out a feed, standing or on scheduled days."""

import io
from datetime import date, datetime

import pytest
from PIL import Image

import Webcam
from Webcam import Webcam as WebcamClass


class RecordingOverlay:
    def __init__(self):
        self.overlayed = None

    def add_overlay(self, buffer, mod_time_str):
        buffer.seek(0)
        self.overlayed = io.BytesIO(buffer.read())


def _frozen_now(monkeypatch, when):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.replace(tzinfo=tz)

    monkeypatch.setattr(Webcam, "datetime", FrozenDatetime)


def _process(monkeypatch, cam):
    def fake_download():
        Image.new("RGB", (40, 20), (200, 30, 30)).save(cam.file_buffer, "JPEG")
        cam.file_buffer.seek(0)

    monkeypatch.setattr(cam, "_download_image", fake_download)
    cam.process()
    overlay = cam.overlays[0]
    overlay.overlayed.seek(0)
    with Image.open(overlay.overlayed) as img:
        return img.convert("RGB").getpixel((20, 10))


@pytest.mark.parametrize(
    "now, blacked_out",
    [
        (datetime(2026, 10, 25, 23, 59), False),
        (datetime(2026, 10, 26, 0, 0), True),
        (datetime(2026, 10, 26, 23, 59), True),
        (datetime(2026, 10, 27, 0, 0), False),
    ],
)
def test_scheduled_blackout_covers_the_mountain_time_day(monkeypatch, now, blacked_out):
    _frozen_now(monkeypatch, now)
    cam = WebcamClass(
        "lpp",
        file_name_on_server="lpp.jpg",
        logo_placements=[RecordingOverlay()],
        blackout_dates=[date(2026, 10, 26)],
    )
    pixel = _process(monkeypatch, cam)
    if blacked_out:
        assert max(pixel) < 10
    else:
        assert pixel[0] > 150


def test_standing_blackout_ignores_the_date(monkeypatch):
    _frozen_now(monkeypatch, datetime(2026, 10, 22, 12, 0))
    cam = WebcamClass(
        "lpp",
        file_name_on_server="lpp.jpg",
        logo_placements=[RecordingOverlay()],
        blackout=True,
    )
    assert max(_process(monkeypatch, cam)) < 10
