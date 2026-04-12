import pytest
import time

import rpicam_z.rpicam_z as camera_module
from rpicam_z.rpicam_z import CAMERA_IMPORT_ERROR, RpiCamZ


def test_importing_module_does_not_create_global_camera_instance():
    assert not hasattr(__import__("rpicam_z.rpicam_z", fromlist=["*"]), "rpicamz")


def test_instantiation_fails_cleanly_when_dependencies_are_missing():
    if CAMERA_IMPORT_ERROR is None:
        pytest.skip("Camera dependencies are available in this environment.")

    with pytest.raises(RuntimeError) as exc_info:
        RpiCamZ()

    assert "Camera dependencies are unavailable" in str(exc_info.value)


class FakeTransform:
    def __init__(self, rotation=0):
        self.rotation = rotation


class FakePicamera2:
    def __init__(self):
        self.sensor_modes = [{"size": (3280, 2464)}]
        self.camera_controls = {}
        self.capture_count = 0
        self.current_config = None
        self.closed = False

    def create_video_configuration(self, main, transform, controls):
        return {
            "kind": "video",
            "main": dict(main),
            "transform": transform,
            "controls": dict(controls),
        }

    def create_still_configuration(self, main, transform, controls):
        return {
            "kind": "still",
            "main": dict(main),
            "transform": transform,
            "controls": dict(controls),
        }

    def configure(self, config):
        self.current_config = config

    def set_controls(self, controls):
        return None

    def start(self):
        return None

    def stop(self):
        return None

    def close(self):
        self.closed = True

    def capture_file(self, buffer, format="jpeg"):
        self.capture_count += 1
        size = self.current_config["main"]["size"]
        kind = self.current_config["kind"]
        payload = f"{kind}:{size[0]}x{size[1]}:{self.capture_count}".encode()
        buffer.write(payload)


class FailingPicamera2(FakePicamera2):
    def capture_file(self, buffer, format="jpeg"):
        raise RuntimeError("capture failed")


def wait_until(predicate, timeout=1.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for expected runtime state.")


@pytest.fixture
def fake_camera(monkeypatch):
    monkeypatch.setattr(camera_module, "CAMERA_IMPORT_ERROR", None)
    monkeypatch.setattr(camera_module, "Picamera2", FakePicamera2)
    monkeypatch.setattr(camera_module, "Transform", FakeTransform)

    camera = RpiCamZ(frame_interval_seconds=0.5, frame_buffer_size=5)
    try:
        yield camera
    finally:
        camera.close()


def test_background_producer_supplies_existing_public_frame_apis(fake_camera):
    first_packet = fake_camera.get_frame_packet()
    capture_count = fake_camera.picam2.capture_count

    second_packet = fake_camera.get_frame_packet()
    jpeg_frame = fake_camera.get_jpeg_frame()

    assert fake_camera.picam2.capture_count == capture_count
    assert second_packet == first_packet
    assert jpeg_frame == first_packet.jpeg_bytes
    assert first_packet.frame_id >= 1


def test_recent_frame_buffer_is_bounded_and_queryable(monkeypatch):
    monkeypatch.setattr(camera_module, "CAMERA_IMPORT_ERROR", None)
    monkeypatch.setattr(camera_module, "Picamera2", FakePicamera2)
    monkeypatch.setattr(camera_module, "Transform", FakeTransform)

    camera = RpiCamZ(frame_interval_seconds=0.01, frame_buffer_size=3)
    try:
        wait_until(lambda: len(camera.get_recent_frames()) == 3)

        recent_frames = camera.get_recent_frames()
        limited_frames = camera.get_recent_frames(limit=2)

        assert len(recent_frames) == 3
        assert [frame.frame_id for frame in recent_frames] == sorted(
            frame.frame_id for frame in recent_frames
        )
        assert limited_frames == recent_frames[-2:]
    finally:
        camera.close()


def test_reconfiguration_and_custom_photo_restart_frame_producer(fake_camera):
    initial_packet = fake_camera.get_frame_packet()
    assert b"video:1640x1232" in initial_packet.jpeg_bytes

    custom_photo = fake_camera.take_custom_photo(5000, 5000)
    assert b"still:3280x2464" in custom_photo

    fake_camera.set_resolution(800, 600)
    reconfigured_packet = wait_until(
        lambda: next(
            (
                packet
                for packet in fake_camera.get_recent_frames()
                if b"video:800x600" in packet.jpeg_bytes
            ),
            None,
        )
    )

    assert reconfigured_packet.frame_id > initial_packet.frame_id
    assert fake_camera._frame_thread is not None
    assert fake_camera._frame_thread.is_alive() is True


def test_get_latest_frame_packet_fails_cleanly_when_no_frame_arrives(monkeypatch):
    monkeypatch.setattr(camera_module, "CAMERA_IMPORT_ERROR", None)
    monkeypatch.setattr(camera_module, "Picamera2", FailingPicamera2)
    monkeypatch.setattr(camera_module, "Transform", FakeTransform)

    camera = RpiCamZ(frame_interval_seconds=0.01, frame_buffer_size=3)
    try:
        with pytest.raises(RuntimeError) as exc_info:
            camera.get_latest_frame_packet(timeout_seconds=0.05)

        assert "No JPEG frame is available" in str(exc_info.value)
        assert camera._frame_thread is not None
        assert camera._frame_thread.is_alive() is True
    finally:
        camera.close()


def test_close_stops_frame_producer_thread(fake_camera):
    fake_camera.get_frame_packet()
    thread = fake_camera._frame_thread

    fake_camera.close()

    assert thread is not None
    assert thread.is_alive() is False
    assert fake_camera.picam2.closed is True
