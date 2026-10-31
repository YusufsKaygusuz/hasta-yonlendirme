"""Interfaces between the camera, the face library and the matcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

Frame = npt.NDArray[np.uint8]
"""An image as an (height, width, 3) array in BGR order, as OpenCV delivers it."""

Encoding = npt.NDArray[np.float64]
"""A face signature: a fixed-length vector (128 values for the dlib model)."""


@dataclass(frozen=True, slots=True)
class DetectedFace:
    top: int
    right: int
    bottom: int
    left: int
    encoding: Encoding

    @property
    def size(self) -> int:
        """The shorter side of the face box, in pixels."""
        return min(self.bottom - self.top, self.right - self.left)

    @property
    def area(self) -> int:
        return (self.bottom - self.top) * (self.right - self.left)


class FaceEncoder(Protocol):
    """Finds faces in a frame and computes one encoding per face."""

    def encode(self, frame: Frame) -> list[DetectedFace]: ...
