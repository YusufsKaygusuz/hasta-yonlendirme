"""Full-screen touch interface built with Tkinter (part of the Python standard library).

Designed for the 5-inch 800x480 touchscreen used in the project, and scales up to
larger displays. The UI only draws :class:`ViewState`; behaviour lives in the controller.
"""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from functools import partial

from hasta_yonlendirme.i18n import Messages
from hasta_yonlendirme.kiosk.controller import RESULT_SCREENS, KioskController, Screen, ViewState
from hasta_yonlendirme.kiosk.worker import CameraFailure, Event, RecognitionWorker

POLL_MS = 50
BASE_WIDTH, BASE_HEIGHT = 800, 480
"""The layout is designed for this size and scaled to the actual window."""

BG = "#0c0d0b"
SURFACE = "#24251f"
SURFACE_PRESSED = "#3a3a33"
BORDER = "#45443d"
TEXT = "#ede8dd"
MUTED = "#8f8b81"
ACCENT = "#f2b33d"
ACCENT_PRESSED = "#c98f22"
ACCENT_TEXT = "#1a1306"
BAD = "#e8826b"
FONT = "DejaVu Sans"


def scale_for(width: int, height: int) -> float:
    """Factor that fits the 800x480 design into a window of the given size."""
    return max(0.6, min(width / BASE_WIDTH, height / BASE_HEIGHT))


class TkKiosk:
    def __init__(
        self,
        controller: KioskController,
        messages: Messages,
        events: queue.Queue[Event],
        worker: RecognitionWorker | None,
        *,
        fullscreen: bool = True,
        hospital_name: str = "",
    ) -> None:
        self.controller = controller
        self.t = messages
        self.events = events
        self.worker = worker
        self.hospital_name = hospital_name
        self.root = tk.Tk()
        self.root.title("Hasta Yönlendirme")
        self.root.configure(bg=BG)
        self.root.geometry(f"{BASE_WIDTH}x{BASE_HEIGHT}")
        self.root.attributes("-fullscreen", fullscreen)
        if fullscreen:
            self.root.config(cursor="none")  # touch screen: no mouse pointer
        self.root.bind("<Control-q>", lambda _e: self.close())
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Key>", self._on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if fullscreen:
            self._scale = scale_for(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        else:
            self._scale = 1.0
        self.root.bind("<Configure>", self._on_resize)
        self._body = tk.Frame(self.root, bg=BG)
        self._body.pack(fill="both", expand=True)
        self._rendered = -1

    # --- loop ------------------------------------------------------------------------------
    def run(self) -> None:
        if self.worker is not None:
            self.worker.start()
        self.root.after(POLL_MS, self._poll)
        self.root.mainloop()

    def close(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.root.destroy()

    def _poll(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, CameraFailure):
                self.controller.on_camera_error()
            else:
                self.controller.on_observation(event)
        self.controller.tick()
        if self.worker is not None:
            busy = self.controller.state.screen in RESULT_SCREENS or self.controller.state.screen is Screen.MANUAL_ENTRY
            self.worker.pause(busy)
        if self.controller.version != self._rendered:
            self._rendered = self.controller.version
            self._render(self.controller.state)
        self.root.after(POLL_MS, self._poll)

    # --- input -----------------------------------------------------------------------------
    def _on_key(self, event: tk.Event[tk.Misc]) -> None:
        """Hardware keyboards and ID-card barcode readers type into the keypad screen."""
        if self.controller.state.screen is not Screen.MANUAL_ENTRY:
            if event.char.isdigit():
                self.controller.open_manual_entry()
            else:
                return
        if event.char.isdigit():
            self.controller.press_digit(event.char)
        elif event.keysym == "BackSpace":
            self.controller.delete_digit()
        elif event.keysym in ("Return", "KP_Enter"):
            self.controller.submit_manual_entry()
        elif event.keysym == "Escape":
            self.controller.cancel_manual_entry()

    def _toggle_fullscreen(self, _event: object = None) -> None:
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def _on_resize(self, event: tk.Event[tk.Misc]) -> None:
        """Scale text to the window, so nothing is cut off after resizing or leaving full screen."""
        if event.widget is not self.root:
            return
        scale = scale_for(event.width, event.height)
        if abs(scale - self._scale) > 0.02:
            self._scale = scale
            self._rendered = -1  # redraw on the next poll

    # --- drawing ---------------------------------------------------------------------------
    def _font(self, size: int, bold: bool = False) -> tuple[str, int, str]:
        return (FONT, round(size * self._scale), "bold" if bold else "normal")

    def _label(self, parent: tk.Misc, text: str, size: int, color: str = TEXT, bold: bool = False) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            fg=color,
            bg=parent["bg"],
            font=self._font(size, bold),
            wraplength=round((BASE_WIDTH - 80) * self._scale),
            justify="center",
        )
        label.pack(pady=round(4 * self._scale))
        return label

    def _button(self, parent: tk.Misc, text: str, command: Callable[[], None], primary: bool = False) -> tk.Label:
        """A touch button drawn as a label.

        Native buttons ignore background colours on macOS (light grey with our light text),
        so a label with click bindings looks the same on every platform.
        """
        bg, pressed = (ACCENT, ACCENT_PRESSED) if primary else (SURFACE, SURFACE_PRESSED)
        button = tk.Label(
            parent,
            text=text,
            font=self._font(18, bold=True),
            fg=ACCENT_TEXT if primary else TEXT,
            bg=bg,
            highlightthickness=1,
            highlightbackground=ACCENT if primary else BORDER,
            padx=round(18 * self._scale),
            pady=round(12 * self._scale),
        )

        def press(_event: object) -> None:
            button.configure(bg=pressed)

        def release(_event: object) -> None:
            button.configure(bg=bg)  # before the command, which may redraw and destroy the button
            command()

        button.bind("<ButtonPress-1>", press)
        button.bind("<ButtonRelease-1>", release)
        return button

    def _render(self, state: ViewState) -> None:
        for child in self._body.winfo_children():
            child.destroy()
        top = tk.Frame(self._body, bg=BG)
        top.pack(fill="x", padx=24, pady=(16, 0))
        tk.Label(top, text=self.hospital_name, fg=MUTED, bg=BG, font=self._font(12)).pack(side="left")
        tk.Label(top, text=self.t("privacy.notice"), fg=MUTED, bg=BG, font=self._font(11)).pack(side="right")

        center = tk.Frame(self._body, bg=BG)
        center.pack(expand=True)
        draw = {
            Screen.IDLE: self._draw_idle,
            Screen.SCANNING: self._draw_scanning,
            Screen.ROUTE: self._draw_route,
            Screen.NO_APPOINTMENT: self._draw_no_appointment,
            Screen.UNRECOGNISED: self._draw_unrecognised,
            Screen.MANUAL_ENTRY: self._draw_manual,
            Screen.CAMERA_ERROR: self._draw_camera_error,
        }[state.screen]
        draw(center, state)

    def _manual_button(self, parent: tk.Misc) -> None:
        self._button(parent, self.t("idle.manual"), self.controller.open_manual_entry).pack(pady=(24, 0))

    def _draw_idle(self, parent: tk.Frame, _state: ViewState) -> None:
        self._label(parent, self.t("idle.title"), 40, bold=True)
        self._label(parent, self.t("idle.body"), 20, MUTED)
        self._manual_button(parent)

    def _draw_scanning(self, parent: tk.Frame, _state: ViewState) -> None:
        self._label(parent, self.t("scanning"), 30, ACCENT, bold=True)

    def _draw_route(self, parent: tk.Frame, state: ViewState) -> None:
        assert state.result is not None
        assert state.result.appointment is not None
        assert state.result.patient is not None
        appt = state.result.appointment
        clinic = appt.clinic
        self._label(parent, self.t("found.greeting", name=state.result.patient.public_name), 20, MUTED)
        location = tk.Frame(parent, bg=BG)
        location.pack(pady=round(6 * self._scale))
        for text in (self.t("location.block", block=clinic.block), self.t("location.floor", floor=clinic.floor)):
            tk.Label(location, text=text, fg=ACCENT, bg=BG, font=self._font(46, bold=True)).pack(side="left", padx=14)
        self._label(parent, clinic.name, 24, bold=True)
        details = [appt.doctor.display_name, self.t("found.time", time=self.t.time(appt.starts_at))]
        if clinic.room:
            details.insert(0, self.t("location.room", room=clinic.room))
        self._label(parent, "  ·  ".join(details), 16, MUTED)
        if clinic.hint:
            self._label(parent, clinic.hint, 16)

    def _draw_no_appointment(self, parent: tk.Frame, _state: ViewState) -> None:
        self._label(parent, self.t("no_appointment.title"), 30, bold=True)
        self._label(parent, self.t("no_appointment.body"), 20, MUTED)

    def _draw_unrecognised(self, parent: tk.Frame, _state: ViewState) -> None:
        self._label(parent, self.t("unknown.title"), 30, bold=True)
        self._label(parent, self.t("unknown.body"), 20, MUTED)
        self._manual_button(parent)

    def _draw_camera_error(self, parent: tk.Frame, _state: ViewState) -> None:
        self._label(parent, self.t("error.camera"), 22, MUTED)
        self._manual_button(parent)

    def _draw_manual(self, parent: tk.Frame, state: ViewState) -> None:
        self._label(parent, self.t("manual.title"), 22, bold=True)
        # Only the last digit is shown, so people waiting behind cannot read the number.
        shown = "•" * max(0, len(state.digits) - 1) + state.digits[-1:]
        self._label(parent, shown or " ", 30, ACCENT, bold=True)
        if state.error_key:
            self._label(parent, self.t(state.error_key), 14, BAD)
        pad = tk.Frame(parent, bg=BG)
        pad.pack(pady=round(4 * self._scale))
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "submit"]
        for i, key in enumerate(keys):
            if key == "clear":
                btn = self._button(pad, self.t("manual.clear"), self.controller.delete_digit)
            elif key == "submit":
                btn = self._button(pad, self.t("manual.submit"), self.controller.submit_manual_entry, primary=True)
            else:
                btn = self._button(pad, key, partial(self.controller.press_digit, key))
            btn.configure(width=6, pady=round(6 * self._scale))
            btn.grid(row=i // 3, column=i % 3, padx=4, pady=4, sticky="nsew")
        self._button(parent, self.t("manual.cancel"), self.controller.cancel_manual_entry).pack(pady=(4, 0))
