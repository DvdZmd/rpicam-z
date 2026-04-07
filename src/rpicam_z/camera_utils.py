from typing import Any, Dict, Tuple


class CameraPresets:
    """Predefined presets for different camera scenarios."""

    RPICAM_HELLO_DEFAULT = {
        "Brightness": 0.0,
        "Contrast": 1.0,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AwbMode": 0,
        "AnalogueGain": 1.0,
    }

    DAYLIGHT = {
        "Brightness": 0.0,
        "Contrast": 1.2,
        "Saturation": 1.1,
        "Sharpness": 1.2,
        "AwbMode": 5,
        "AnalogueGain": 1.0,
    }

    INDOOR = {
        "Brightness": 0.1,
        "Contrast": 1.1,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AwbMode": 1,
        "AnalogueGain": 2.0,
    }

    LOW_LIGHT = {
        "Brightness": 0.2,
        "Contrast": 0.9,
        "Saturation": 0.8,
        "Sharpness": 0.8,
        "AwbMode": 0,
        "AnalogueGain": 4.0,
        "DigitalGain": 2.0,
    }

    HIGH_CONTRAST = {
        "Brightness": 0.0,
        "Contrast": 2.0,
        "Saturation": 1.3,
        "Sharpness": 1.5,
        "AwbMode": 0,
    }

    TIMELAPSE = {
        "Brightness": 0.0,
        "Contrast": 1.0,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AfMode": 2,
        "AwbMode": 0,
    }

    NEUTRAL_WARM = {
        "Brightness": 0.0,
        "Contrast": 1.0,
        "Saturation": 0.9,
        "Sharpness": 1.0,
        "AwbMode": 5,
        "AnalogueGain": 1.0,
    }

    LED_LIGHTING = {
        "Brightness": 0.0,
        "Contrast": 1.1,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AwbMode": 4,
        "AnalogueGain": 1.5,
    }

    LUNAR_PHOTOGRAPHY = {
        "AeEnable": False,
        "AnalogueGain": 1.0,
        "ExposureTime": 10000,
        "Brightness": 0.0,
        "Contrast": 1.5,
        "AfMode": 0,
    }


class CameraControlLimits:
    """Limits and ranges for camera controls."""

    BRIGHTNESS = (-1.0, 1.0)
    CONTRAST = (0.0, 32.0)
    SATURATION = (0.0, 32.0)
    SHARPNESS = (0.0, 16.0)
    ANALOGUE_GAIN = (1.0, 10.666667)
    DIGITAL_GAIN = (1.0, 64.0)
    LENS_POSITION = (0.0, 32.0)

    EXPOSURE_TIME_MIN = 75
    EXPOSURE_TIME_MAX = 1238765

    AWB_MODES = {
        0: "Auto",
        1: "Incandescent",
        2: "Tungsten",
        3: "Fluorescent",
        4: "Indoor",
        5: "Daylight",
        6: "Cloudy",
        7: "Custom",
    }

    AE_MODES = {
        True: "On",
        False: "Off",
    }

    EXPOSURE_VALUE = (-8.0, 8.0)

    AF_MODES = {
        0: "Manual",
        1: "Auto",
        2: "Continuous",
    }


def validate_control_value(control_name: str, value: Any) -> Tuple[bool, Any]:
    """
    Validate and normalize a camera control value.

    Returns a tuple of ``(is_valid, adjusted_value)``.
    """
    limits = CameraControlLimits()

    if control_name == "Brightness":
        min_val, max_val = limits.BRIGHTNESS
        return True, max(min_val, min(max_val, float(value)))

    if control_name == "Contrast":
        min_val, max_val = limits.CONTRAST
        return True, max(min_val, min(max_val, float(value)))

    if control_name == "Saturation":
        min_val, max_val = limits.SATURATION
        return True, max(min_val, min(max_val, float(value)))

    if control_name == "Sharpness":
        min_val, max_val = limits.SHARPNESS
        return True, max(min_val, min(max_val, float(value)))

    if control_name == "AnalogueGain":
        min_val, max_val = limits.ANALOGUE_GAIN
        return True, max(min_val, min(max_val, float(value)))

    if control_name == "DigitalGain":
        min_val, max_val = limits.DIGITAL_GAIN
        return True, max(min_val, min(max_val, float(value)))

    if control_name == "LensPosition":
        min_val, max_val = limits.LENS_POSITION
        return True, max(min_val, min(max_val, float(value)))

    if control_name == "ExposureTime":
        if value is None:
            return True, None
        return True, max(limits.EXPOSURE_TIME_MIN, min(limits.EXPOSURE_TIME_MAX, int(value)))

    if control_name == "AwbMode":
        if int(value) in limits.AWB_MODES:
            return True, int(value)
        return False, 0

    if control_name == "AfMode":
        if int(value) in limits.AF_MODES:
            return True, int(value)
        return False, 2

    if control_name == "AeEnable":
        return True, bool(value)

    return True, value


def get_control_info() -> Dict[str, Dict[str, Any]]:
    """Describe the supported camera controls for API consumers."""
    limits = CameraControlLimits()

    return {
        "Brightness": {
            "range": limits.BRIGHTNESS,
            "type": "float",
            "description": "Adjust image brightness (-1.0 = very dark, 1.0 = very bright)",
            "default": 0.0,
        },
        "Contrast": {
            "range": limits.CONTRAST,
            "type": "float",
            "description": "Adjust image contrast (0.0 = no contrast, 2.0+ = high contrast)",
            "default": 1.0,
        },
        "Saturation": {
            "range": limits.SATURATION,
            "type": "float",
            "description": "Adjust color saturation (0.0 = grayscale, 2.0+ = highly saturated)",
            "default": 1.0,
        },
        "Sharpness": {
            "range": limits.SHARPNESS,
            "type": "float",
            "description": "Adjust image sharpness (0.0 = very soft, 2.0+ = very sharp)",
            "default": 1.0,
        },
        "AnalogueGain": {
            "range": limits.ANALOGUE_GAIN,
            "type": "float",
            "description": "Sensor analog gain (1.0 = no gain, higher values = more sensitivity/noise)",
            "default": 1.0,
        },
        "DigitalGain": {
            "range": limits.DIGITAL_GAIN,
            "type": "float",
            "description": "Digital gain (1.0 = no gain, higher values = more brightness but more noise)",
            "default": 1.0,
        },
        "LensPosition": {
            "range": limits.LENS_POSITION,
            "type": "float",
            "description": "Manual focus position (0.0 = infinity, 32.0 = very close)",
            "default": None,
        },
        "ExposureTime": {
            "range": (limits.EXPOSURE_TIME_MIN, limits.EXPOSURE_TIME_MAX),
            "type": "int",
            "description": "Exposure time in microseconds (None = automatic)",
            "default": None,
        },
        "AwbMode": {
            "options": limits.AWB_MODES,
            "type": "int",
            "description": "Automatic white balance mode",
            "default": 0,
        },
        "AfMode": {
            "options": limits.AF_MODES,
            "type": "int",
            "description": "Autofocus mode",
            "default": 2,
        },
    }


__all__ = [
    "CameraControlLimits",
    "CameraPresets",
    "get_control_info",
    "validate_control_value",
]
