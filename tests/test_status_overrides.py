"""Unit tests for the comms-tools status overrides file."""

import json
import logging
from datetime import date

import pytest

from config import apply_status_overrides, load_config

YAML = """
webcams:
  - name: lpp
    file_name_on_server: lpp.jpg
    status_note: Sensor down for winter
    logo_placements: []
  - name: mg
    file_name_on_server: mg.jpg
    blackout_dates: [2026-11-01]
    logo_placements: []
allsky_videos:
  - name: allsky
    file_name_on_server: allsky.mp4
    logo_place: [0, 619]
    logo_size: [299, 68]
"""


@pytest.fixture
def config(tmp_path):
    cfg = tmp_path / "webcams.yaml"
    cfg.write_text(YAML)
    return load_config(str(cfg))


def _apply(config, tmp_path, data):
    path = tmp_path / "status-overrides.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return apply_status_overrides(config, str(path))


def _by_name(config):
    return {c.name: c for c in [*config.webcams, *config.allsky_videos]}


def test_missing_file_leaves_config_alone(config, tmp_path):
    assert apply_status_overrides(config, str(tmp_path / "absent.json")) == config


def test_present_keys_replace_yaml_and_absent_keys_keep_it(config, tmp_path):
    cams = _by_name(
        _apply(
            config,
            tmp_path,
            {
                "cameras": {
                    "lpp": {"blackout": True, "status_note_until": "2026-11-15"},
                    "mg": {
                        "blackout_dates": ["2026-11-02"],
                        "status_note": "Lens iced over",
                    },
                    "allsky": {"status_note": "Dome fogged"},
                }
            },
        )
    )

    assert cams["lpp"].blackout is True
    assert cams["lpp"].status_note == "Sensor down for winter"
    assert cams["lpp"].status_note_until == date(2026, 11, 15)
    assert cams["mg"].blackout_dates == [date(2026, 11, 2)]
    assert cams["mg"].status_note == "Lens iced over"
    assert cams["allsky"].status_note == "Dome fogged"


def test_null_clears_a_yaml_value(config, tmp_path):
    cams = _by_name(
        _apply(config, tmp_path, {"cameras": {"lpp": {"status_note": None}}})
    )
    assert cams["lpp"].status_note is None


@pytest.mark.parametrize(
    "entry",
    [
        {"blackout": "yes"},
        {"blackout_dates": "2026-11-02"},
        {"blackout_dates": ["next week"]},
        {"status_note": ""},
        {"status_note_until": "soon"},
        {"status_note": "fine", "typo": 1},
        "not an object",
    ],
)
def test_a_bad_entry_skips_only_that_camera(config, tmp_path, caplog, entry):
    with caplog.at_level(logging.WARNING):
        cams = _by_name(
            _apply(
                config,
                tmp_path,
                {"cameras": {"lpp": entry, "mg": {"status_note": "Still applied"}}},
            )
        )

    assert cams["lpp"] == _by_name(config)["lpp"]
    assert cams["mg"].status_note == "Still applied"
    assert "Ignoring status overrides for lpp" in caplog.text


def test_allsky_videos_take_no_blackout(config, tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        cams = _by_name(
            _apply(config, tmp_path, {"cameras": {"allsky": {"blackout": True}}})
        )
    assert not hasattr(cams["allsky"], "blackout")
    assert "Ignoring status overrides for allsky" in caplog.text


@pytest.mark.parametrize(
    "data", ["{not json", "[]", {"cameras": []}, {"cameras": {}, "extra": 1}]
)
def test_a_malformed_file_is_ignored_whole(config, tmp_path, caplog, data):
    with caplog.at_level(logging.WARNING):
        assert _apply(config, tmp_path, data) == config
    assert "Ignoring status overrides in" in caplog.text


def test_unknown_camera_is_reported(config, tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        _apply(config, tmp_path, {"cameras": {"renamed": {"blackout": True}}})
    assert "unknown camera 'renamed'" in caplog.text
