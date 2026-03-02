import io, time, threading, os
from datetime import datetime
from picamera2 import Picamera2
from libcamera import Transform
from camera.camera_utils import validate_control_value # Importamos el validador

class CameraController:
    def __init__(self, width=1640, height=1232, rotation=0, save_path="captures"):
        self.picam2 = Picamera2()
        self.save_path = save_path
        
        # Estado inicial
        self.current_width = width
        self.current_height = height
        self.current_rotation = rotation
        self.is_running = False
        self.af_supported = False
        self.max_sensor_res = (width, height)
        
        self.controls = {
            "Brightness": 0.0,
            "Contrast": 1.0,
            "Saturation": 1.0,
            "Sharpness": 1.0
        }

        self.lock = threading.Lock()
        self.timelapse_active = False
        
        # 1. Detectar capacidades antes de arrancar
        self._detect_sensor_limits()
        # 2. Iniciar hardware
        self._initialize_camera()

    def _detect_sensor_limits(self):
        try:
            modes = self.picam2.sensor_modes
            if modes:
                w = max(m['size'][0] for m in modes)
                h = max(m['size'][1] for m in modes)
                self.max_sensor_res = (w, h)
        except:
            pass


    def _initialize_camera(self):
        with self.lock:
            if self.is_running:
                self.picam2.stop()
            
            config = self.picam2.create_video_configuration(
                main={"size": (self.current_width, self.current_height), "format": "XRGB8888"},
                transform=self._get_transform(self.current_rotation)
            )
            self.picam2.configure(config)
            
            if "AfMode" in self.picam2.camera_controls:
                self.af_supported = True
                if "AfMode" not in self.controls:
                    self.controls["AfMode"] = 2
            
            self.picam2.set_controls(self.controls)
            self.picam2.start()
            self.is_running = True


    def get_capabilities(self):
        """Retorna las capacidades usando los datos cacheados"""
        # Ya no llamamos a self.picam2.sensor_modes aquí para evitar el error
        return {
            "max_width": self.max_sensor_res[0],
            "max_height": self.max_sensor_res[1],
            "af_supported": self.af_supported,
            "current_width": self.current_width,
            "current_height": self.current_height
        }

    def _get_transform(self, angle):
        """Retorna el objeto Transform de libcamera adecuado"""
        mapping = {
            0: Transform(), # Identity
            90: Transform(rotation=90),
            180: Transform(rotation=180),
            270: Transform(rotation=270)
        }
        return mapping.get(angle, Transform())

    def set_resolution(self, width, height):
        with self.lock:
            self.current_width = width
            self.current_height = height
            self._initialize_camera()

    def take_snapshot(self):
        """Captura una imagen JPEG de alta calidad"""
        with self.lock:
            # Captura directamente del stream actual
            buf = io.BytesIO()
            self.picam2.capture_file(buf, format="jpeg")
            return buf.getvalue()


    def update_control(self, name, value):
        """Valida y aplica cambios de hardware"""

        # Evitar que el JS intente mover el AF si la cámara no puede
        if name == "AfMode" and not self.af_supported:
            return
        

        is_valid, adjusted_value = validate_control_value(name, value)
        if is_valid:
            with self.lock:
                self.controls[name] = adjusted_value
                self.picam2.set_controls({name: adjusted_value})
                # Si es AfMode manual, podrías querer resetear el LensPosition aquí

    def set_rotation(self, angle):
        """Cambia la rotación reiniciando el stream (requerido por libcamera)"""
        if angle in [0, 90, 180, 270]:
            self.current_rotation = angle
            self.picam2.stop()
            self._initialize_camera() # Aplica el nuevo transform

    def take_custom_photo(self, width, height):
        """Captura una foto a resolución específica y restaura el stream original"""
        with self.lock:
            # 1. Guardar configuración actual del stream
            old_w, old_h = self.current_width, self.current_height
            
            try:
                # 2. Detener stream y configurar resolución de la FOTO
                self.picam2.stop()
                
                # Validar que no exceda el máximo del sensor
                max_w, max_h = self.max_sensor_res
                target_w = min(int(width), max_w)
                target_h = min(int(height), max_h)

                still_config = self.picam2.create_still_configuration(
                    main={"size": (target_w, target_h), "format": "XRGB8888"},
                    transform=self._get_transform(self.current_rotation)
                )
                self.picam2.configure(still_config)
                self.picam2.start()
                
                # 3. Capturar frame
                buf = io.BytesIO()
                self.picam2.capture_file(buf, format="jpeg")
                data = buf.getvalue()
                return data
                
            finally:
                # 4. RESTAURAR siempre el stream original
                self.picam2.stop()
                self.current_width, self.current_height = old_w, old_h
                self._initialize_camera()

    def get_jpeg_frame(self):
        """Captura directa del ISP a memoria (máxima calidad)"""
        buf = io.BytesIO()
        # El hardware ya procesó rotación y calidad antes de entregarnos este buffer
        self.picam2.capture_file(buf, format="jpeg")
        return buf.getvalue()

    # --- Lógica de Timelapse ---
    def start_timelapse(self, interval_seconds, width=None, height=None):
        """
        Inicia el timelapse. 
        Si no se pasan width/height, usará la resolución máxima del sensor.
        """
        if not self.timelapse_active:
            # Si no se define resolución, usamos el máximo detectado
            t_width = width or self.max_sensor_res[0]
            t_height = height or self.max_sensor_res[1]
            
            self.timelapse_active = True
            self.timelapse_thread = threading.Thread(
                target=self._timelapse_worker, 
                args=(interval_seconds, t_width, t_height),
                daemon=True
            )
            self.timelapse_thread.start()

    def stop_timelapse(self):
        self.timelapse_active = False
        
    def _timelapse_worker(self, interval, width, height):
        save_path = "captures/timelapse"
        os.makedirs(save_path, exist_ok=True)
        
        while self.timelapse_active:
            # Usamos take_custom_photo para que cambie la resolución, 
            # capture a alta calidad y restaure el stream automáticamente.
            frame = self.take_custom_photo(width, height)
            
            if frame:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{save_path}/shot_{timestamp}.jpg"
                with open(filename, "wb") as f:
                    f.write(frame)
            
            # El tiempo de espera debe considerar que take_custom_photo 
            # tarda ~1-2 segundos en resetear la cámara
            time.sleep(max(1, interval))

camera_controller = CameraController()