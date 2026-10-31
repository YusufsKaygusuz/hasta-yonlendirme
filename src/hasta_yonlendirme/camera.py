"""Camera access for USB webcams (OpenCV) and the Raspberry Pi camera module (Picamera2)."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from hasta_yonlendirme.config import CameraConfig
from hasta_yonlendirme.recognition.base import Frame


class CameraError(RuntimeError):
    pass


class Camera(Protocol):
    def read(self) -> Frame:
        """Return the latest frame in BGR order. Raises CameraError on failure."""
        ...

    def close(self) -> None: ...


class OpenCVCamera:
    """USB and V4L2 cameras, and the built-in webcam on a development laptop."""

    def __init__(self, device: int = 0, width: int = 640, height: int = 480) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise CameraError("OpenCV is not installed. Run: pip install 'hasta-yonlendirme[camera]'") from exc
        self._cv2 = cv2
        self._capture: Any = cv2.VideoCapture(device)
        if not self._capture.isOpened():
            raise CameraError(f"Could not open camera {device}")
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        # Keep only the newest frame so recognition never works on a stale image.
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> Frame:
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise CameraError("Could not read a frame from the camera")
        return np.asarray(frame, dtype=np.uint8)

    def close(self) -> None:
        self._capture.release()


class PiCamera:
    """Raspberry Pi Camera Module (v2, v3) through libcamera / Picamera2.

    On Raspberry Pi OS Bookworm the CSI camera is not reachable through OpenCV's
    V4L2 backend; Picamera2 is the supported route (``sudo apt install python3-picamera2``).
    """

    def __init__(self, width: int = 640, height: int = 480) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise CameraError("Picamera2 is not installed. Run: sudo apt install python3-picamera2") from exc
        self._camera: Any = Picamera2()
        # Picamera2's "RGB888" format is laid out as BGR in memory, which is what we want.
        config = self._camera.create_preview_configuration(main={"format": "RGB888", "size": (width, height)})
        self._camera.configure(config)
        self._camera.start()

    def read(self) -> Frame:
        try:
            frame = self._camera.capture_array()
        except Exception as exc:
            raise CameraError("Could not read a frame from the Pi camera") from exc
        return np.asarray(frame, dtype=np.uint8)

    def close(self) -> None:
        self._camera.stop()
        self._camera.close()


def open_camera(config: CameraConfig) -> Camera:
    if config.backend == "picamera2":
        return PiCamera(config.width, config.height)
    return OpenCVCamera(config.device, config.width, config.height)
