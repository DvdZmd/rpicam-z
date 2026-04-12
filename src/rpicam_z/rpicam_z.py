import io
import logging
import os
import threading
import time
from collections import deque
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
        width=1640,
        height=1232,
        rotation=0,
        save_path="captures",
        frame_interval_seconds=0.033,
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
        self.frame_interval_seconds = max(0.01, float(frame_interval_seconds))
        self._frame_buffer_size = max(1, int(frame_buffer_size))
        self._frame_thread = None
        self._frame_thread_running = False
        self._frame_stop_event = threading.Event()
        self._frame_condition = threading.Condition()
        self._frame_generation = 0
        self._latest_frame = None
        self._frame_buffer = deque(maxlen=self._frame_buffer_size)
        self._frame_wait_timeout_seconds = max(0.1, self.frame_interval_seconds * 3)
        self._last_capture_duration_ms = None
        self._last_publish_wall_time_ns = None

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

    def _reset_frame_cache(self):
        """Clear cached frames so callers never observe stale stream data."""
        with self._frame_condition:
            self._latest_frame = None
            self._frame_buffer.clear()
            self._last_publish_wall_time_ns = None

    def _start_frame_producer(self):
        """Start the background JPEG producer for the active camera pipeline."""
        with self._frame_condition:
            thread = self._frame_thread
            if thread and thread.is_alive():
                return
            self._frame_stop_event.clear()
            self._frame_generation += 1
            frame_generation = self._frame_generation
            self._frame_thread_running = True
            self._frame_thread = threading.Thread(
                target=self._frame_worker,
                args=(frame_generation,),
                name="rpicam-z-frame-producer",
                daemon=True,
            )
            self._frame_thread.start()

    def _stop_frame_producer(self):
        """Stop the background JPEG producer and wait briefly for it to exit."""
        with self._frame_condition:
            thread = self._frame_thread
            self._frame_thread_running = False
            self._frame_generation += 1
            self._frame_stop_event.set()
            self._frame_condition.notify_all()

        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.frame_interval_seconds * 10))

        with self._frame_condition:
            if self._frame_thread is thread:
                self._frame_thread = None

    def _reconfigure_camera(self):
        """Restart the camera pipeline and its frame producer cleanly."""
        self._stop_frame_producer()
        self._reset_frame_cache()
        with self.lock:
            self._configure_running_camera_locked()
        self._start_frame_producer()

    def close(self):
        """Stop background work and release the camera cleanly."""
        self.stop_timelapse()
        self._stop_frame_producer()
        self._reset_frame_cache()
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
        self._stop_frame_producer()
        self._reset_frame_cache()
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
        self._start_frame_producer()

    def _capture_jpeg_bytes(self) -> bytes:
        """Capture a JPEG into memory.

        This helper expects the caller to hold ``self.lock`` when thread safety
        matters.
        """
        buf = io.BytesIO()
        self.picam2.capture_file(buf, format="jpeg")
        return buf.getvalue()

    def _capture_frame_packet_locked(self) -> FramePacket:
        """Capture a JPEG frame and build a packet while holding ``self.lock``."""
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

    def _store_frame_packet(self, frame_packet: FramePacket, frame_generation: int) -> None:
        """Publish a captured frame to latest-frame state and recent buffer."""
        with self._frame_condition:
            if frame_generation != self._frame_generation or not self._frame_thread_running:
                return
            self._latest_frame = frame_packet
            self._last_publish_wall_time_ns = time.time_ns()
            self._frame_buffer.append(frame_packet)
            self._frame_condition.notify_all()

    def _frame_worker(self, frame_generation: int) -> None:
        """Capture JPEG frames continuously while the camera pipeline is active."""
        while not self._frame_stop_event.is_set():
            started_monotonic = time.monotonic()
            try:
                with self.lock:
                    if not self.is_running:
                        break
                    capture_started_ns = time.monotonic_ns()
                    frame_packet = self._capture_frame_packet_locked()
                    capture_finished_ns = time.monotonic_ns()
                self._last_capture_duration_ms = (
                    capture_finished_ns - capture_started_ns
                ) / 1_000_000
                self._store_frame_packet(frame_packet, frame_generation)
            except Exception:
                logger.exception("Continuous frame capture failed; retrying shortly.")
                if self._frame_stop_event.wait(max(self.frame_interval_seconds, 0.1)):
                    break
                continue

            elapsed = time.monotonic() - started_monotonic
            sleep_seconds = max(0.0, self.frame_interval_seconds - elapsed)
            if self._frame_stop_event.wait(sleep_seconds):
                break

        with self._frame_condition:
            if frame_generation == self._frame_generation:
                self._frame_thread_running = False
            self._frame_condition.notify_all()

    def _wait_for_latest_frame(self, timeout_seconds: float | None = None) -> FramePacket:
        """Wait briefly for the next available frame packet."""
        latest_frame = self._latest_frame
        if latest_frame is not None:
            return latest_frame

        wait_timeout = (
            self._frame_wait_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        with self._frame_condition:
            has_frame = self._frame_condition.wait_for(
                lambda: self._latest_frame is not None or not self._frame_thread_running,
                timeout=wait_timeout,
            )
            if has_frame and self._latest_frame is not None:
                return self._latest_frame

        raise RuntimeError("No JPEG frame is available from the continuous producer.")

    def get_latest_frame_packet(self, timeout_seconds: float | None = None) -> FramePacket:
        """Return the most recent frame produced by the background capture thread."""
        return self._wait_for_latest_frame(timeout_seconds=timeout_seconds)

    def get_frame_producer_status(self) -> dict[str, int | float | None]:
        """Return a compact snapshot of producer timing and publication state."""
        latest_frame = self._latest_frame
        return {
            "frame_id": None if latest_frame is None else latest_frame.frame_id,
            "last_capture_duration_ms": self._last_capture_duration_ms,
            "last_publish_wall_time_ns": self._last_publish_wall_time_ns,
        }

    def get_recent_frames(self, limit: int | None = None) -> list[FramePacket]:
        """Return a snapshot of recent frame packets from the local ring buffer."""
        with self._frame_condition:
            frames = list(self._frame_buffer)

        if limit is None:
            return frames
        return frames[-max(0, int(limit)) :]

    def get_frame_packet(self) -> FramePacket:
        """Return the most recent background-produced frame packet."""
        return self.get_latest_frame_packet()

    def get_jpeg_frame(self) -> bytes:
        """Return the JPEG payload from the latest background-produced frame."""
        return self.get_latest_frame_packet().jpeg_bytes

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
