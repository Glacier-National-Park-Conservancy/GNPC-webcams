#! /usr/bin/python3

"""
Controls the operation of the program to add logos to and upload webcam photos
and videos from the glacier.org FTP server to HTML server.
"""

import logging
import os
import sys
import threading
import traceback
from datetime import datetime
from time import sleep

from dotenv import load_dotenv

from logging_config import install_status_notes, setup_logging
from paths import resolve_path

load_dotenv(resolve_path("environment.env"))
setup_logging()
logger = logging.getLogger(__name__)

from config import (
    apply_status_overrides,
    create_allsky_video_from_config,
    create_webcam_from_config,
    load_config,
)
from single_instance import AlreadyRunning, SingleInstance
from Webcam import MOUNTAIN_TIME, Webcam

# Load configuration from YAML, then the blackout and status-note changes made
# in comms-tools, which writes them to an untracked file beside the checkout
OVERRIDES_FILE = os.getenv("STATUS_OVERRIDES_FILE", "status-overrides.json")
yaml_config = load_config("webcams.yaml")
app_config = apply_status_overrides(yaml_config, OVERRIDES_FILE)

# Create webcam objects from configuration
webcams = [
    create_webcam_from_config(webcam_config) for webcam_config in app_config.webcams
]
allsky_videos = [
    create_allsky_video_from_config(video_config)
    for video_config in app_config.allsky_videos
]

# Combine all cameras
cams = webcams + allsky_videos

status_notes = app_config.active_status_notes(datetime.now(MOUNTAIN_TIME).date())
install_status_notes(status_notes)


def refresh_status():
    """Bring blackouts and status notes up to date with the overrides file.

    comms-tools can rewrite it at any moment. Re-reading it before each round,
    not once per run, gets a change onto glacier.org within about half a minute.
    Updated in place: StatusNoteFilter and handle_cam hold this same dict.
    """
    config = apply_status_overrides(yaml_config, OVERRIDES_FILE)
    by_name = {c.name: c for c in config.webcams}
    for cam in webcams:
        cam.blackout = by_name[cam.name].blackout
        cam.blackout_dates = frozenset(by_name[cam.name].blackout_dates)
    status_notes.clear()
    status_notes.update(config.active_status_notes(datetime.now(MOUNTAIN_TIME).date()))


# Seconds to idle between the two rounds of a run. Cron fires every minute and
# only one run executes at a time, so a run has to finish inside its minute or
# the next tick is skipped by the lock. Two rounds plus this gap must leave room
# for the slowest round.
ROUND_INTERVAL = 25


def handle_cam(cam: Webcam):
    try:
        logger.info(f"Starting processing for {cam.name}...")
        cam.process()
        cam.upload_image()
        logger.info(f"Completed {cam.name}")

    except Exception:
        note = status_notes.get(cam.name)
        known = f" [known issue: {note}]" if note else ""
        return f"{cam.name} failed.{known} {traceback.format_exc()}"


def main():
    threads = []
    errors = []

    for cam in cams:
        # Named for the camera so StatusNoteFilter can tell whose records are whose.
        thread = threading.Thread(
            name=cam.name, target=lambda cam=cam: errors.append(handle_cam(cam))
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    errors = [item for item in errors if item is not None]
    if errors:
        error_message = "\n\n".join(errors)
        # stderr so cron emails errors even when stdout is redirected to /dev/null
        print(error_message, file=sys.stderr)


if __name__ == "__main__":
    try:
        with SingleInstance():
            try:
                for i in range(2):
                    if i:
                        # Idle between rounds without holding FTP sessions. The
                        # server allows only a few connections per IP, so a
                        # process that sits on its connections while sleeping
                        # starves anything else using them.
                        Webcam._close_connections()
                        sleep(ROUND_INTERVAL)
                        refresh_status()
                    main()
            finally:
                Webcam._close_connections()
    except AlreadyRunning as e:
        # Not an error: the previous run is still working and the next cron tick
        # will cover this cycle. Stays off stderr so cron doesn't email it.
        logger.info(f"Skipping run: {e}")
