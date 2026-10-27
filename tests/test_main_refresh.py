"""main.refresh_status: overrides re-read between a run's rounds."""

import importlib
import json
import logging

import pytest


@pytest.fixture
def main(monkeypatch):
    # environment.env may point logging at a file; importing main loads it,
    # but never overrides what is already set.
    monkeypatch.setenv("LOG_OUTPUT", "console")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    module = importlib.import_module("main")
    yield module
    for handler in logging.root.handlers[:]:
        handler.close()
        logging.root.removeHandler(handler)


def test_refresh_picks_up_a_change_made_after_the_run_started(
    main, monkeypatch, tmp_path
):
    overrides = tmp_path / "status-overrides.json"
    monkeypatch.setattr(main, "OVERRIDES_FILE", str(overrides))
    lpp = next(cam for cam in main.webcams if cam.name == "lpp")
    yaml_note = main.yaml_config.active_status_notes(main.datetime.now().date())["lpp"]

    overrides.write_text(
        json.dumps(
            {
                "cameras": {
                    "lpp": {
                        "blackout": True,
                        "blackout_dates": ["2026-11-02"],
                        "status_note": "Camera bumped",
                    }
                }
            }
        )
    )
    main.refresh_status()
    assert lpp.blackout is True
    assert "2026-11-02" in {d.isoformat() for d in lpp.blackout_dates}
    assert main.status_notes["lpp"] == "Camera bumped"

    overrides.unlink()
    main.refresh_status()
    assert lpp.blackout is False
    assert lpp.blackout_dates == frozenset()
    assert main.status_notes["lpp"] == yaml_note
