# Raspberry Pi setup

This guide builds the kiosk used in the project: a Raspberry Pi 4 with the camera module,
a 5-inch 800×480 HDMI touchscreen and a small USB speaker.

## 1. Operating system

Flash **Raspberry Pi OS (64-bit), Bookworm** with Raspberry Pi Imager. In the imager's
settings, set a user name, Wi-Fi or Ethernet, and enable SSH. Then:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo raspi-config   # Display Options → Screen Blanking → No
```

Connect the touchscreen and follow its manufacturer's instructions for the display and touch
driver, including rotation if you mount it in portrait.

## 2. System packages

```bash
sudo apt install -y git python3-venv python3-tk python3-opencv python3-picamera2 \
    espeak-ng cmake build-essential libopenblas-dev liblapack-dev
```

OpenCV and Picamera2 come from apt because they are built for the Pi's camera stack.
Check the camera:

```bash
rpicam-hello --timeout 3000
```

## 3. More swap for building dlib

Compiling dlib needs more memory than a 2 GB Pi has. Temporarily raise the swap file:

```bash
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup && sudo dphys-swapfile swapon
```

Set it back to `100` after step 4 to spare the SD card.

## 4. Install the kiosk

```bash
git clone https://github.com/YusufsKaygusuz/hasta-yonlendirme.git ~/hasta-yonlendirme
cd ~/hasta-yonlendirme
python3 -m venv --system-site-packages .venv   # sees apt's OpenCV and Picamera2
source .venv/bin/activate
pip install -e ".[face]"                       # dlib compiles here; this takes a long time
```

## 5. Secrets and configuration

```bash
sudo mkdir -p /etc/hasta-yonlendirme
echo "HY_ID_PEPPER=$(openssl rand -hex 32)" | sudo tee /etc/hasta-yonlendirme/env > /dev/null
sudo chown root:$USER /etc/hasta-yonlendirme/env && sudo chmod 640 /etc/hasta-yonlendirme/env
sudo cp config/hasta-yonlendirme.example.toml /etc/hasta-yonlendirme/config.toml
```

Edit `/etc/hasta-yonlendirme/config.toml`:

```toml
[kiosk]
hospital_name = "Your Hospital"

[camera]
backend = "picamera2"

[database]
path = "/home/<user>/hasta-yonlendirme/data/hasta-yonlendirme.db"
```

**Back up the pepper.** If it is lost, stored ID hashes can no longer be matched and every
patient must be enrolled again. If it leaks, rotate it and re-enrol.

For MySQL, set `backend = "mysql"` with the host, database and user, add
`HY_DB_PASSWORD=...` to the env file, and run `hasta-yonlendirme init-db` once from an
administrator account (see [privacy.md](privacy.md#database-accounts)).

## 6. Try it

```bash
set -a; source /etc/hasta-yonlendirme/env; set +a
hasta-yonlendirme init-db
hasta-yonlendirme check-camera          # frames per second including face detection
hasta-yonlendirme run                   # Ctrl+Q quits, F11 toggles full screen
```

If the frame rate is low, lower `recognition.downscale` (for example `0.4`) or the camera
resolution.

## 7. Start on boot

Install the user service shipped in [`deploy/`](../deploy):

```bash
mkdir -p ~/.config/systemd/user
cp deploy/hasta-yonlendirme.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hasta-yonlendirme
sudo loginctl enable-linger $USER      # start without anyone logging in over SSH
journalctl --user -u hasta-yonlendirme -f
```

The service waits for the desktop session and restarts the kiosk if it ever exits. Enable
desktop auto-login in `raspi-config` (System Options → Boot / Auto Login) so the session
starts after a power cut.

## Troubleshooting

| Symptom | Check |
|---|---|
| "Picamera2 is not installed" | The virtual environment was created without `--system-site-packages`. |
| Camera error screen | `rpicam-hello` works? Ribbon cable seated, blue side towards the Ethernet port? |
| No sound | `espeak-ng -v tr "deneme"`; choose the USB speaker as the default audio output. |
| Window opens on the wrong display | Set `DISPLAY=:0` in the service file. |
| Faces not found | Light the face from the front; avoid strong light behind the patient. Lower `min_face_size` if the camera is mounted far away. |
