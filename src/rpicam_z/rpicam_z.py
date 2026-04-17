import io
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from rpicam_z.camera_utils import CameraPresets, validate_control_value

logger = logging.getLogger(__name__)
CAMERA_IMPORT_ERROR = None

try:
    from picamera2 import Picamera2
    from libcamera import Transform
except ModuleNotFoundError as exc:
    Picamera2 = None
    Transform = None
    CAMERA_IMPORT_ERROR = exc


@dataclass(frozen=True)
class FramePacket:
    """JPEG frame payload enriched with capture identifiers and timestamps."""

    frame_id: int
    jpeg_bytes: bytes
    captured_wall_time_ns: int
    captured_monotonic_ns: int


class RpiCamZ:
    """
    Reusable Raspberry Pi camera controller built on Picamera2.

    The camera is initialized when an instance is created, not when the module
    is imported. This keeps the package safe to import in environments without
    camera hardware.
    """

    def __init__(
        self,
        width=1280,
        height=720,
        rotation=0,
        save_path="captures",
        frame_interval_seconds=0.1,
        frame_buffer_size=60,
    ):
        if CAMERA_IMPORT_ERROR is not None:
            raise RuntimeError(
                "Camera dependencies are unavailable. Original import error: "
                f"{CAMERA_IMPORT_ERROR}"
            ) from CAMERA_IMPORT_ERROR

        self.picam2 = Picamera2()
        self.default_config = {
            "width": width,
            "height": height,
            "rotation": rotation,
            "controls": {
                "Brightness": 0.0,
                "Contrast": 1.0,
                "Saturation": 1.0,
                "Sharpness": 1.0,
                "AeEnable": True,
            },
        }
        self.max_sensor_res = (width, height)
        self.controls = dict(self.default_config["controls"])
        self.current_width = width
        self.current_height = height
        self.current_rotation = rotation
        self.save_path = save_path

        self.is_running = False
        self.af_supported = False
        self.lock = threading.Lock()
        self.timelapse_thread = None
        self.timelapse_active = False
        self._frame_counter = 0

        self._detect_sensor_limits()
        self._reconfigure_camera()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def _detect_sensor_limits(self):
        """Cache the maximum sensor resolution reported by Picamera2."""
        try:
            modes = self.picam2.sensor_modes
            if modes:
                width = max(mode["size"][0] for mode in modes)
                height = max(mode["size"][1] for mode in modes)
                self.max_sensor_res = (width, height)
        except Exception as exc:
            logger.debug("Unable to detect sensor limits: %s", exc)

    def _configure_running_camera_locked(self):
        """Configure and start the camera using the current settings."""
        if self.is_running:
            self.picam2.stop()
            self.is_running = False

        config = self.picam2.create_video_configuration(
            main={"size": (self.current_width, self.current_height), "format": "XRGB8888"},
            transform=self._get_transform(self.current_rotation),
            controls=self.controls,
        )
        self.picam2.configure(config)

        available_controls = self.picam2.camera_controls
        if "AfMode" in available_controls:
            self.af_supported = True
            self.controls["AfMode"] = 2
            logger.info("Autofocus-capable camera detected.")
        else:
            self.af_supported = False
            self.controls.pop("AfMode", None)
            self.controls.pop("LensPosition", None)
            logger.info("Fixed-focus camera detected.")

        self.picam2.set_controls(self.controls)
        self.picam2.start()
        self.is_running = True

    def _reconfigure_camera(self):
        """Restart the camera pipeline cleanly with the current settings."""
        with self.lock:
            self._configure_running_camera_locked()

    def close(self):
        """Stop background work and release the camera cleanly."""
        self.stop_timelapse()
        with self.lock:
            if self.is_running:
                self.picam2.stop()
                self.is_running = False
            close_method = getattr(self.picam2, "close", None)
            if callable(close_method):
                close_method()

    def reset_to_defaults(self):
        """Restore the initial stream configuration and camera controls."""
        self.current_width = self.default_config["width"]
        self.current_height = self.default_config["height"]
        self.current_rotation = self.default_config["rotation"]
        self.controls = dict(self.default_config["controls"])
        if self.af_supported:
            self.controls["AfMode"] = 2
        self._reconfigure_camera()

    def apply_preset(self, preset_name):
        """Apply a preset from ``CameraPresets`` to the active camera."""
        preset = getattr(CameraPresets, preset_name, None)
        if not preset:
            return False

        filtered_preset = dict(preset)
        if not self.af_supported:
            filtered_preset.pop("AfMode", None)
            filtered_preset.pop("LensPosition", None)

        with self.lock:
            self.controls.update(filtered_preset)
            self.picam2.set_controls(filtered_preset)
        return True

    def get_capabilities(self):
        """Return cached camera capabilities and current stream state."""
        return {
            "max_width": self.max_sensor_res[0],
            "max_height": self.max_sensor_res[1],
            "af_supported": self.af_supported,
            "current_width": self.current_width,
            "current_height": self.current_height,
        }

    def _get_transform(self, angle):
        """Build a libcamera transform for a supported rotation."""
        mapping = {
            0: Transform(),
            90: Transform(rotation=90),
            180: Transform(rotation=180),
            270: Transform(rotation=270),
        }
        return mapping.get(angle, Transform())

    def set_resolution(self, width, height):
        """Update the stream resolution and restart the camera pipeline."""
        self.current_width = int(width)
        self.current_height = int(height)
        self._reconfigure_camera()

    def take_snapshot(self):
        """Capture a JPEG frame from the current stream."""
        with self.lock:
            return self._capture_jpeg_bytes()

    def update_control(self, name, value):
        """Validate and apply a camera control change."""
        if name == "AfMode" and not self.af_supported:
            return False

        is_valid, adjusted_value = validate_control_value(name, value)
        if not is_valid:
            return False

        with self.lock:
            self.controls[name] = adjusted_value
            if name in ["ExposureTime", "AnalogueGain"]:
                self.controls["AeEnable"] = False
                self.picam2.set_controls({"AeEnable": False, name: adjusted_value})
            else:
                self.picam2.set_controls({name: adjusted_value})
        return True

    def set_rotation(self, angle):
        """Change stream rotation and restart the camera pipeline."""
        if angle not in [0, 90, 180, 270]:
            return False

        self.current_rotation = angle
        self._reconfigure_camera()
        return True

    def take_custom_photo(self, width, height):
        """Capture a still JPEG at a requested resolution and restore the stream."""
        with self.lock:
            old_width, old_height = self.current_width, self.current_height
            try:
                if self.is_running:
                    self.picam2.stop()
                    self.is_running = False

                max_width, max_height = self.max_sensor_res
                target_width = min(int(width), max_width)
                target_height = min(int(height), max_height)

                still_config = self.picam2.create_still_configuration(
                    main={"size": (target_width, target_height), "format": "XRGB8888"},
                    transform=self._get_transform(self.current_rotation),
                    controls=self.controls,
                )
                self.picam2.configure(still_config)
                self.picam2.start()
                self.is_running = True

                return self._capture_jpeg_bytes()
            finally:
                if self.is_running:
                    self.picam2.stop()
                    self.is_running = False
                self.current_width, self.current_height = old_width, old_height
                self._configure_running_camera_locked()

    def _capture_jpeg_bytes(self) -> bytes:
        """Capture a JPEG into memory.

        This helper expects the caller to hold ``self.lock`` when thread safety
        matters.
        """
        buf = io.BytesIO()
        self.picam2.capture_file(buf, format="jpeg")
        return buf.getvalue()

    def _capture_frame_packet_locked(self) -> FramePacket:
        """Capture a JPEG frame packet on demand while holding ``self.lock``."""
        jpeg_bytes = self._capture_jpeg_bytes()
        captured_wall_time_ns = time.time_ns()
        captured_monotonic_ns = time.monotonic_ns()
        self._frame_counter += 1
        return FramePacket(
            frame_id=self._frame_counter,
            jpeg_bytes=jpeg_bytes,
            captured_wall_time_ns=captured_wall_time_ns,
            captured_monotonic_ns=captured_monotonic_ns,
        )

    def get_frame_packet(self) -> FramePacket:
        """Capture and return a JPEG frame packet on demand."""
        with self.lock:
            return self._capture_frame_packet_locked()

    def get_jpeg_frame(self) -> bytes:
        """Capture and return a JPEG frame on demand."""
        return self.get_frame_packet().jpeg_bytes

    def start_timelapse(self, interval_seconds, width=None, height=None):
        """Start a background timelapse capture thread."""
        if self.timelapse_active:
            return False

        target_width = width or self.max_sensor_res[0]
        target_height = height or self.max_sensor_res[1]
        self.timelapse_active = True
        self.timelapse_thread = threading.Thread(
            target=self._timelapse_worker,
            args=(interval_seconds, target_width, target_height),
            daemon=True,
        )
        self.timelapse_thread.start()
        return True

    def stop_timelapse(self):
        """Request timelapse shutdown and wait briefly for the worker to exit."""
        self.timelapse_active = False
        thread = self.timelapse_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1)
        self.timelapse_thread = None

    def _timelapse_worker(self, interval, width, height):
        """Capture timelapse frames and persist them to disk."""
        os.makedirs(self.save_path, exist_ok=True)

        while self.timelapse_active:
            frame = self.take_custom_photo(width, height)
            if frame:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(self.save_path, f"shot_{timestamp}.jpg")
                with open(filename, "wb") as file_obj:
                    file_obj.write(frame)
            time.sleep(max(1, interval))


class UnavailableCamera:
    """Placeholder object returned when camera dependencies are unavailable."""

    def __init__(self, error):
        self.error = error

    def get_capabilities(self):
        return {
            "available": False,
            "error": str(self.error),
        }

    def __getattr__(self, name):
        raise RuntimeError(
            "Camera is unavailable because its dependencies could not be imported: "
            f"{self.error}"
        ) from self.error


CameraController = RpiCamZ
rpicam_z = RpiCamZ

__all__ = [
    "CAMERA_IMPORT_ERROR",
    "CameraController",
    "FramePacket",
    "RpiCamZ",
    "UnavailableCamera",
    "rpicam_z",
]
