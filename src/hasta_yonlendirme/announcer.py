"""Speaking the route out loud, for patients who cannot easily read the screen.

Two offline engines are supported: espeak-ng (Raspberry Pi and Linux) and the built-in
``say`` command on macOS, which is handy on a development machine. Without either, the
kiosk stays silent and keeps working.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from typing import Protocol

log = logging.getLogger(__name__)

# macOS voices per kiosk language; any other value of [audio] voice is used as is.
MAC_VOICES = {"tr": "Yelda", "en": "Samantha"}


class Announcer(Protocol):
    def say(self, text: str) -> None: ...


class SilentAnnouncer:
    def say(self, text: str) -> None:
        pass


class _ProcessAnnouncer:
    """Runs a speech command in the background; a new announcement interrupts the previous one."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None

    def _command(self, text: str) -> list[str]:
        raise NotImplementedError

    def say(self, text: str) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        try:
            self._process = subprocess.Popen(  # noqa: S603 - fixed executable, text passed as one argument
                self._command(text),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            log.exception("Text-to-speech failed")


class EspeakAnnouncer(_ProcessAnnouncer):
    """espeak-ng: offline, speaks Turkish. Install with ``sudo apt install espeak-ng``."""

    def __init__(self, voice: str, speed: int = 150, executable: str | None = None) -> None:
        super().__init__()
        found = executable or shutil.which("espeak-ng") or shutil.which("espeak")
        if found is None:
            raise FileNotFoundError("espeak-ng is not installed")
        self.executable = found
        self.voice = voice
        self.speed = speed

    def _command(self, text: str) -> list[str]:
        return [self.executable, "-v", self.voice, "-s", str(self.speed), text]


class MacSayAnnouncer(_ProcessAnnouncer):
    """The ``say`` command built into macOS (Turkish voice: Yelda)."""

    def __init__(self, voice: str, speed: int = 150, executable: str | None = None) -> None:
        super().__init__()
        found = executable or shutil.which("say")
        if found is None:
            raise FileNotFoundError("say is not available")
        self.executable = found
        self.voice = MAC_VOICES.get(voice, voice)
        self.speed = speed

    def _command(self, text: str) -> list[str]:
        return [self.executable, "-v", self.voice, "-r", str(self.speed), text]


def make_announcer(enabled: bool, voice: str, speed: int) -> Announcer:
    """The first available engine: espeak-ng, then macOS ``say``, otherwise silence."""
    if not enabled:
        return SilentAnnouncer()
    try:
        return EspeakAnnouncer(voice, speed)
    except FileNotFoundError:
        pass
    if sys.platform == "darwin":
        try:
            return MacSayAnnouncer(voice, speed)
        except FileNotFoundError:
            pass
    log.warning("No text-to-speech engine found (install espeak-ng); spoken directions are disabled")
    return SilentAnnouncer()
