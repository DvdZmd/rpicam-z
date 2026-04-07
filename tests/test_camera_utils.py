from rpicam_z import CameraPresets, get_control_info, validate_control_value


def test_validate_control_value_clamps_numeric_values():
    is_valid, adjusted = validate_control_value("Brightness", 10)
    assert is_valid is True
    assert adjusted == 1.0


def test_validate_control_value_rejects_invalid_awb_mode():
    is_valid, adjusted = validate_control_value("AwbMode", 99)
    assert is_valid is False
    assert adjusted == 0


def test_get_control_info_contains_expected_fields():
    info = get_control_info()
    assert "Brightness" in info
    assert info["ExposureTime"]["type"] == "int"


def test_presets_are_exposed():
    assert CameraPresets.DAYLIGHT["AwbMode"] == 5
