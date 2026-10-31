"""Command-line interface: run the kiosk and administer its data.

hasta-yonlendirme init-db
hasta-yonlendirme demo
hasta-yonlendirme enroll --first-name Ayşe --last-name Demir --photo ayse.jpg --consent
hasta-yonlendirme run
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from hasta_yonlendirme import __version__
from hasta_yonlendirme.config import Config, ConfigError, load_config
from hasta_yonlendirme.identity import InvalidNationalIdError, MissingPepperError, NationalIdHasher
from hasta_yonlendirme.storage import Repository, open_repository

log = logging.getLogger("hasta_yonlendirme")


class CommandError(Exception):
    """An expected failure with a message for the operator; exits with status 1."""


def _national_id(args: argparse.Namespace) -> str:
    # Prompting keeps the number out of shell history and process listings.
    return args.national_id or getpass.getpass("National ID number (hidden): ")


def _hasher(config: Config) -> NationalIdHasher:
    return NationalIdHasher.from_env(config.privacy.pepper_env)


def _patient_id(repo: Repository, hasher: NationalIdHasher, national_id: str) -> int:
    patient_id = repo.find_patient_id(hasher.hash(national_id))
    if patient_id is None:
        raise CommandError("No patient is registered with that ID number.")
    return patient_id


# --- commands --------------------------------------------------------------------------------
def cmd_init_db(config: Config, _args: argparse.Namespace) -> None:
    repo = open_repository(config.database)
    try:
        repo.create_schema()
    finally:
        repo.close()
    print(f"Database ready ({config.database.backend}).")


def cmd_demo(config: Config, _args: argparse.Namespace) -> None:
    from hasta_yonlendirme.demo import seed_demo_data

    repo = open_repository(config.database)
    try:
        repo.create_schema()
        patients = seed_demo_data(repo, _hasher(config))
    finally:
        repo.close()
    print("Demo clinics, doctors and patients created. Try these ID numbers on the kiosk keypad:")
    for p in patients:
        note = "appointment later today" if p.has_appointment else "no appointment"
        print(f"  {p.national_id}  {p.first_name} {p.last_name}  ({note})")


def cmd_enroll(config: Config, args: argparse.Namespace) -> None:
    if not args.consent:
        raise CommandError(
            "Biometric data needs the patient's explicit consent (KVKK art. 6 / GDPR art. 9). "
            "Collect it, then repeat the command with --consent."
        )
    from hasta_yonlendirme.recognition.dlib_backend import EnrollmentError, encode_photo

    hasher = _hasher(config)
    id_hash = hasher.hash(_national_id(args))
    try:
        encodings = [encode_photo(Path(p), config.recognition.detection_model) for p in args.photo]
    except EnrollmentError as exc:
        raise CommandError(str(exc)) from exc

    repo = open_repository(config.database)
    try:
        patient_id = repo.find_patient_id(id_hash)
        if patient_id is None:
            patient_id = repo.add_patient(args.first_name, args.last_name, id_hash, consent_at=datetime.now())
        for encoding in encodings:
            repo.add_encoding(patient_id, encoding, model=f"dlib-{config.recognition.detection_model}")
    finally:
        repo.close()
    print(f"Enrolled patient #{patient_id} with {len(encodings)} face encoding(s). The photos were not stored.")


def cmd_add_clinic(config: Config, args: argparse.Namespace) -> None:
    repo = open_repository(config.database)
    try:
        clinic_id = repo.add_clinic(args.name, args.block, args.floor, args.room, args.hint)
    finally:
        repo.close()
    print(f"Clinic #{clinic_id} added.")


def cmd_add_doctor(config: Config, args: argparse.Namespace) -> None:
    repo = open_repository(config.database)
    try:
        doctor_id = repo.add_doctor(args.name, args.title)
    finally:
        repo.close()
    print(f"Doctor #{doctor_id} added.")


def cmd_add_appointment(config: Config, args: argparse.Namespace) -> None:
    try:
        starts_at = datetime.strptime(args.at, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise CommandError('--at must look like "2026-11-02 14:30"') from exc
    hasher = _hasher(config)
    national_id = _national_id(args)
    repo = open_repository(config.database)
    try:
        patient_id = _patient_id(repo, hasher, national_id)
        appointment_id = repo.add_appointment(patient_id, args.doctor, args.clinic, starts_at)
    finally:
        repo.close()
    print(f"Appointment #{appointment_id} added.")


def cmd_forget(config: Config, args: argparse.Namespace) -> None:
    hasher = _hasher(config)
    national_id = _national_id(args)
    repo = open_repository(config.database)
    try:
        deleted = repo.delete_face_data(_patient_id(repo, hasher, national_id))
    finally:
        repo.close()
    print(f"Deleted {deleted} face encoding(s). The patient can still use the ID-number path.")


def cmd_check_camera(config: Config, args: argparse.Namespace) -> None:
    from hasta_yonlendirme.camera import CameraError, open_camera

    try:
        camera = open_camera(config.camera)
    except CameraError as exc:
        raise CommandError(str(exc)) from exc
    encoder = None
    try:
        from hasta_yonlendirme.recognition.dlib_backend import DlibFaceEncoder, FaceLibraryMissingError

        encoder = DlibFaceEncoder(config.recognition.detection_model, config.recognition.downscale)
    except FaceLibraryMissingError:
        print("Face library not installed: measuring the camera only.")
    try:
        started = time.perf_counter()
        for i in range(args.frames):
            frame = camera.read()
            faces = len(encoder.encode(frame)) if encoder else "-"
            print(f"frame {i + 1:>3}: {frame.shape[1]}x{frame.shape[0]}  faces: {faces}")
        elapsed = time.perf_counter() - started
    finally:
        camera.close()
    print(f"{args.frames / elapsed:.1f} frames per second including detection.")


def cmd_run(config: Config, args: argparse.Namespace) -> None:
    from hasta_yonlendirme.kiosk.app import run_kiosk

    run_kiosk(config, headless=args.headless)


# --- parser ----------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hasta-yonlendirme",
        description="Contactless patient wayfinding kiosk for hospitals.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-c", "--config", type=Path, help="TOML config file (default: ./hasta-yonlendirme.toml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = sub.add_parser("run", help="start the kiosk")
    run.add_argument("--headless", action="store_true", help="text interface instead of the touch screen")
    run.set_defaults(handler=cmd_run)

    sub.add_parser("init-db", help="create the database tables").set_defaults(handler=cmd_init_db)
    sub.add_parser("demo", help="create tables and fill them with fictional sample data").set_defaults(handler=cmd_demo)

    enroll = sub.add_parser("enroll", help="register a patient's face (photos are not stored)")
    enroll.add_argument("--first-name", required=True)
    enroll.add_argument("--last-name", required=True)
    enroll.add_argument("--national-id", help="prompted for if omitted (recommended)")
    enroll.add_argument("--photo", required=True, action="append", help="photo with only the patient; repeatable")
    enroll.add_argument("--consent", action="store_true", help="confirm the patient gave explicit consent")
    enroll.set_defaults(handler=cmd_enroll)

    clinic = sub.add_parser("add-clinic", help="add a clinic and where to find it")
    clinic.add_argument("--name", required=True)
    clinic.add_argument("--block", required=True)
    clinic.add_argument("--floor", required=True)
    clinic.add_argument("--room", default="")
    clinic.add_argument("--hint", default="", help='directions, e.g. "Turn right out of the lift"')
    clinic.set_defaults(handler=cmd_add_clinic)

    doctor = sub.add_parser("add-doctor", help="add a doctor")
    doctor.add_argument("--name", required=True)
    doctor.add_argument("--title", default="")
    doctor.set_defaults(handler=cmd_add_doctor)

    appointment = sub.add_parser("add-appointment", help="book an appointment (for testing)")
    appointment.add_argument("--national-id", help="prompted for if omitted")
    appointment.add_argument("--clinic", type=int, required=True, help="clinic id")
    appointment.add_argument("--doctor", type=int, required=True, help="doctor id")
    appointment.add_argument("--at", required=True, help='"YYYY-MM-DD HH:MM"')
    appointment.set_defaults(handler=cmd_add_appointment)

    forget = sub.add_parser("forget", help="erase a patient's face data (consent withdrawn)")
    forget.add_argument("--national-id", help="prompted for if omitted")
    forget.set_defaults(handler=cmd_forget)

    check = sub.add_parser("check-camera", help="test the camera and measure the frame rate")
    check.add_argument("--frames", type=int, default=30)
    check.set_defaults(handler=cmd_check_camera)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        config = load_config(args.config)
        args.handler(config, args)
    except (CommandError, ConfigError, MissingPepperError, InvalidNationalIdError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
