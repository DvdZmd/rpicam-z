from typing import Dict, Any, Tuple

class CameraPresets:
    """Presets predefinidos para diferentes escenarios de cámara"""
    
    # Preset que replica exactamente rpicam-hello defaults
    RPICAM_HELLO_DEFAULT = {
        "Brightness": 0.0,
        "Contrast": 1.0,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AwbMode": 0,
        "AnalogueGain": 1.0
    }
    
    DAYLIGHT = {
        "Brightness": 0.0,
        "Contrast": 1.2,
        "Saturation": 1.1,
        "Sharpness": 1.2,
        "AwbMode": 5,
        "AnalogueGain": 1.0
    }
    
    INDOOR = {
        "Brightness": 0.1,
        "Contrast": 1.1,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AwbMode": 1,
        "AnalogueGain": 2.0
    }
    
    LOW_LIGHT = {
        "Brightness": 0.2,
        "Contrast": 0.9,
        "Saturation": 0.8,
        "Sharpness": 0.8,
        "AwbMode": 0,
        "AnalogueGain": 4.0,
        "DigitalGain": 2.0
    }
    
    HIGH_CONTRAST = {
        "Brightness": 0.0,
        "Contrast": 2.0,
        "Saturation": 1.3,
        "Sharpness": 1.5,
        "AwbMode": 0
    }
    
    TIMELAPSE = {
        "Brightness": 0.0,
        "Contrast": 1.0,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AfMode": 2,
        "AwbMode": 0
    }
    
    NEUTRAL_WARM = {
        "Brightness": 0.0,
        "Contrast": 1.0,
        "Saturation": 0.9,
        "Sharpness": 1.0,
        "AwbMode": 5,
        "AnalogueGain": 1.0
    }
    
    LED_LIGHTING = {
        "Brightness": 0.0,
        "Contrast": 1.1,
        "Saturation": 1.0,
        "Sharpness": 1.0,
        "AwbMode": 4,
        "AnalogueGain": 1.5
    }


class CameraControlLimits:
    """Límites y rangos para controles de cámara"""
    
    BRIGHTNESS = (-1.0, 1.0)
    CONTRAST = (0.0, 32.0)
    SATURATION = (0.0, 32.0)
    SHARPNESS = (0.0, 16.0)
    ANALOGUE_GAIN = (1.0, 10.666667)
    DIGITAL_GAIN = (1.0, 64.0)
    LENS_POSITION = (0.0, 32.0)  # 0.0 = infinity, 32.0 = closest
    
    # Exposure time in microseconds
    EXPOSURE_TIME_MIN = 75
    EXPOSURE_TIME_MAX = 1238765  # ~1.24s
    
    # AWB modes
    AWB_MODES = {
        0: "Auto",
        1: "Incandescent", 
        2: "Tungsten",
        3: "Fluorescent",
        4: "Indoor",
        5: "Daylight",
        6: "Cloudy",
        7: "Custom"
    }
    
    # Exposure Value compensation
    EXPOSURE_VALUE = (-8.0, 8.0)  # EV compensation range
    
    # AF modes  
    AF_MODES = {
        0: "Manual",
        1: "Auto",
        2: "Continuous"
    }


def validate_control_value(control_name: str, value: Any) -> Tuple[bool, Any]:
    """
    Valida y ajusta valores de control dentro de rangos permitidos
    
    Args:
        control_name: Nombre del control
        value: Valor a validar
        
    Returns:
        Tuple[bool, Any]: (is_valid, adjusted_value)
    """
    limits = CameraControlLimits()
    
    if control_name == "Brightness":
        min_val, max_val = limits.BRIGHTNESS
        adjusted = max(min_val, min(max_val, float(value)))
        return True, adjusted
        
    elif control_name == "Contrast":
        min_val, max_val = limits.CONTRAST
        adjusted = max(min_val, min(max_val, float(value)))
        return True, adjusted
        
    elif control_name == "Saturation":
        min_val, max_val = limits.SATURATION
        adjusted = max(min_val, min(max_val, float(value)))
        return True, adjusted
        
    elif control_name == "Sharpness":
        min_val, max_val = limits.SHARPNESS
        adjusted = max(min_val, min(max_val, float(value)))
        return True, adjusted
        
    elif control_name == "AnalogueGain":
        min_val, max_val = limits.ANALOGUE_GAIN
        adjusted = max(min_val, min(max_val, float(value)))
        return True, adjusted
        
    elif control_name == "DigitalGain":
        min_val, max_val = limits.DIGITAL_GAIN
        adjusted = max(min_val, min(max_val, float(value)))
        return True, adjusted
        
    elif control_name == "LensPosition":
        min_val, max_val = limits.LENS_POSITION
        adjusted = max(min_val, min(max_val, float(value)))
        return True, adjusted
        
    elif control_name == "ExposureTime":
        if value is None:
            return True, None  # Auto exposure
        adjusted = max(limits.EXPOSURE_TIME_MIN, 
                      min(limits.EXPOSURE_TIME_MAX, int(value)))
        return True, adjusted
        
    elif control_name == "AwbMode":
        if int(value) in limits.AWB_MODES:
            return True, int(value)
        return False, 0
        
    elif control_name == "AfMode":
        if int(value) in limits.AF_MODES:
            return True, int(value)
        return False, 2
    
    # For other controls, return as-is
    return True, value


def get_control_info() -> Dict[str, Dict[str, Any]]:
    """
    Retorna información detallada sobre todos los controles disponibles
    
    Returns:
        Dict con información de cada control (rangos, descripción, etc.)
    """
    limits = CameraControlLimits()
    
    return {
        "Brightness": {
            "range": limits.BRIGHTNESS,
            "type": "float",
            "description": "Ajusta el brillo de la imagen (-1.0 = muy oscuro, 1.0 = muy brillante)",
            "default": 0.0
        },
        "Contrast": {
            "range": limits.CONTRAST,
            "type": "float", 
            "description": "Ajusta el contraste de la imagen (0.0 = sin contraste, 2.0+ = alto contraste)",
            "default": 1.0
        },
        "Saturation": {
            "range": limits.SATURATION,
            "type": "float",
            "description": "Ajusta la saturación de color (0.0 = escala de grises, 2.0+ = muy saturado)",
            "default": 1.0
        },
        "Sharpness": {
            "range": limits.SHARPNESS, 
            "type": "float",
            "description": "Ajusta la nitidez de la imagen (0.0 = muy suave, 2.0+ = muy nítido)",
            "default": 1.0
        },
        "AnalogueGain": {
            "range": limits.ANALOGUE_GAIN,
            "type": "float",
            "description": "Ganancia analógica del sensor (1.0 = sin ganancia, valores altos = más sensibilidad/ruido)",
            "default": 1.0
        },
        "DigitalGain": {
            "range": limits.DIGITAL_GAIN,
            "type": "float", 
            "description": "Ganancia digital (1.0 = sin ganancia, valores altos = más brillo pero más ruido)",
            "default": 1.0
        },
        "LensPosition": {
            "range": limits.LENS_POSITION,
            "type": "float",
            "description": "Posición manual del enfoque (0.0 = infinito, 32.0 = muy cerca)",
            "default": None
        },
        "ExposureTime": {
            "range": (limits.EXPOSURE_TIME_MIN, limits.EXPOSURE_TIME_MAX),
            "type": "int",
            "description": "Tiempo de exposición en microsegundos (None = automático)",
            "default": None
        },
        "AwbMode": {
            "options": limits.AWB_MODES,
            "type": "int",
            "description": "Modo de balance de blancos automático",
            "default": 0
        },
        "AfMode": {
            "options": limits.AF_MODES,
            "type": "int", 
            "description": "Modo de enfoque automático",
            "default": 2
        }
    }