import rpicam_z


def test_public_api_exports_expected_symbols():
    assert rpicam_z.RpiCamZ is rpicam_z.CameraController
    assert rpicam_z.rpicam_z is rpicam_z.RpiCamZ
    assert "RpiCamZ" in rpicam_z.__all__
    assert "CameraPresets" in rpicam_z.__all__


def test_unavailable_camera_reports_error():
    camera = rpicam_z.UnavailableCamera(RuntimeError("missing camera stack"))
    capabilities = camera.get_capabilities()

    assert capabilities["available"] is False
    assert "missing camera stack" in capabilities["error"]
