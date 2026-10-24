"""Point pydiagral at the fake Diagral cloud while a marker file exists.

Installed into the Home Assistant venv next to a one-line .pth file, so Python
imports it at startup. Without the marker it does nothing. With it, it
reassigns pydiagral.api.BASE_URL — read by pydiagral at every request — and
logs a warning each time a DiagralAPI is created, so the redirect shows up in
home-assistant.log and cannot be forgotten silently.
"""

import contextlib
import logging
import os
from pathlib import Path

MARKER = Path(
    os.environ.get(
        "DIAGRAL_FAKE_CLOUD_MARKER",
        "/workspaces/home-assistant-dev/config/.diagral_fake_cloud",
    )
)


def _redirect() -> None:
    if not MARKER.is_file():
        return
    url = MARKER.read_text(encoding="utf-8").strip()
    if not url:
        return

    import pydiagral.api  # noqa: PLC0415

    pydiagral.api.BASE_URL = url
    original_init = pydiagral.api.DiagralAPI.__init__

    def init_with_warning(self, *args, **kwargs):
        logging.getLogger("pydiagral.api").warning(
            "DIAGRAL FAKE CLOUD ACTIVE: all pydiagral calls go to %s (marker %s)",
            url,
            MARKER,
        )
        original_init(self, *args, **kwargs)

    pydiagral.api.DiagralAPI.__init__ = init_with_warning


# Never break interpreter startup in the Home Assistant venv.
with contextlib.suppress(Exception):
    _redirect()
