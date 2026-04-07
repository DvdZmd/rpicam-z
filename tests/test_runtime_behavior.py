import pytest

from rpicam_z.rpicam_z import CAMERA_IMPORT_ERROR, RpiCamZ


def test_importing_module_does_not_create_global_camera_instance():
    assert not hasattr(__import__("rpicam_z.rpicam_z", fromlist=["*"]), "rpicamz")


def test_instantiation_fails_cleanly_when_dependencies_are_missing():
    if CAMERA_IMPORT_ERROR is None:
        pytest.skip("Camera dependencies are available in this environment.")

    with pytest.raises(RuntimeError) as exc_info:
        RpiCamZ()

    assert "Camera dependencies are unavailable" in str(exc_info.value)
