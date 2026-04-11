from .camera_utils import CameraPresets, get_control_info, validate_control_value
from .rpicam_z import FramePacket, RpiCamZ, UnavailableCamera

# Backwards-compatible aliases for earlier API names.
CameraController = RpiCamZ
rpicam_z = RpiCamZ

__all__ = [
    "CameraController",
    "CameraPresets",
    "FramePacket",
    "RpiCamZ",
    "UnavailableCamera",
    "get_control_info",
    "rpicam_z",
    "validate_control_value",
]
