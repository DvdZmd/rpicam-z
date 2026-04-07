# RpiCamZ

`RpiCamZ` is a reusable Python package for Raspberry Pi camera projects built on top of `picamera2`.

It is intended to live as its own library repository and be reused from other IoT applications through `pip`, while keeping Raspberry Pi camera setup requirements explicit and predictable.

## Features

- Stream configuration and resolution changes
- JPEG snapshots and custom-resolution photos
- Camera control validation helpers
- Built-in presets for common lighting scenarios
- Timelapse capture to disk
- Safe imports in non-camera environments

## Installation

### 1. Install Raspberry Pi camera prerequisites

`libcamera` is required at the system level, but it should not be installed as a normal Python dependency of this package.

On Raspberry Pi OS, the recommended setup is:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-libcamera libcamera-apps
```

If you want to use a virtual environment, prefer:

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
```

### 2. Install the library

```bash
pip install RpiCamZ
```

For local development:

```bash
pip install -r requirements.txt
```

## Why `libcamera` is not in `dependencies`

`RpiCamZ` imports Python bindings from `libcamera`, but those bindings depend on the Raspberry Pi system camera stack and version matching at the OS level.

In practice:

- `libcamera` is a system prerequisite
- `picamera2` is the Python-facing library dependency
- Raspberry Pi OS packages are the most reliable way to install the camera stack

## Quick Start

```python
from rpicam_z import RpiCamZ

with RpiCamZ(width=1280, height=720) as camera:
    camera.apply_preset("DAYLIGHT")
    jpeg_bytes = camera.take_snapshot()

with open("snapshot.jpg", "wb") as f:
    f.write(jpeg_bytes)
```

## Public API

Main exports:

- `RpiCamZ`
- `CameraController` as a backwards-compatible alias
- `CameraPresets`
- `validate_control_value`
- `get_control_info`

## Notes for Reuse in IoT Projects

- Importing the package does not start the camera.
- Camera access begins when `RpiCamZ()` is instantiated.
- On non-Raspberry-Pi environments, import is safe, but creating a camera instance will raise a runtime error if camera dependencies are unavailable.

## Testing

The test suite focuses on import safety and helper logic so it can run without camera hardware:

```bash
pytest
```
