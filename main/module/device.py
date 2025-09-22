import base64
import fcntl
import json
import os
import platform
import time

import cv2
import numpy as np
from serial import Serial
from serial.tools import list_ports

from module.aws.apigateway import ApiGatewayConnector
from module.utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)
webcam_logger = setup_custom_logger("webcam")
# Constants for settings
DETECTED_WEBCAM_PORT = 0  # Assuming webcam is at port 0; adjust as needed
WARMUP_SECONDS = 10  # Time for camera auto-adjustment in darkness
TMP_FOLDER = "/tmp"
TEMP_DATA_FILE_PATH = "/container_storage/temporary_device_data.json"

# Get environment variables
apigateway_url = os.getenv("API_GATEWAY_MILJOSTASJON_URL")
apigateway_key = os.getenv("API_GATEWAY_MILJOSTASJON_KEY")
device_id = os.getenv("DEVICE_ID")

# Instantiate API Gateway connector
apigateway = ApiGatewayConnector(base_url=apigateway_url, api_key=apigateway_key)


class Webcam:
    def __init__(self, port=DETECTED_WEBCAM_PORT, tmp_folder=TMP_FOLDER):
        self.port = port
        self.tmp_folder = tmp_folder
        self.cap = None  # Will be initialized when needed
        webcam_logger.info(f"Webcam initialized with port {self.port}.")

    def initialize_camera(self):
        """
        Initializes the camera, ensuring any previously opened capture is released.
        """
        if self.cap is not None:
            self.cap.release()
            cv2.destroyAllWindows()
            time.sleep(1)  # Allow time for the camera to reset

        self.cap = cv2.VideoCapture(self.port)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"JPEG"))

        if not self.cap.isOpened():
            webcam_logger.error("Failed to open webcam.")
            return False
        return True

    def trigger_webcam(self):
        """
        Warm up camera for WARMUP_SECONDS, then capture one image,
        save it locally, and send to API.
        """
        if not self.initialize_camera():
            return

        try:
            # Try to enable auto settings (driver dependent, may be ignored)
            for prop, val in [
                (cv2.CAP_PROP_AUTO_EXPOSURE, 0.75),
                (cv2.CAP_PROP_AUTO_WB, 1),
                (cv2.CAP_PROP_GAIN, -1),
            ]:
                try:
                    self.cap.set(prop, val)
                except Exception:
                    pass

            # Warm up camera so auto-exposure can stabilize
            start = time.monotonic()
            last_frame = None
            while time.monotonic() - start < WARMUP_SECONDS:
                ret, frame = self.cap.read()
                if ret:
                    last_frame = frame

            # Capture final frame (fallback to last valid warmup frame)
            ret, frame = self.cap.read()
            frame = frame if ret else last_frame
            if frame is None:
                webcam_logger.error("Failed to capture frame after warmup.")
                return

            # Save and send image
            image_path = self.save_image(frame)
            self.send_image_to_api(image_path)

        except Exception as e:
            webcam_logger.exception(f"Error while capturing/sending image: {e}")
        finally:
            self.release_resources()

    def save_image(self, image):
        if not os.path.exists(self.tmp_folder):
            os.makedirs(self.tmp_folder)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(self.tmp_folder, f"webcam_capture_{timestamp}.jpg")
        cv2.imwrite(image_path, image, [cv2.IMWRITE_JPEG_QUALITY, 100])
        webcam_logger.info(f"Image saved to {image_path}.")
        return image_path

    def send_image_to_api(self, image_path):
        try:
            with open(image_path, "rb") as img_file:
                base64_string = base64.b64encode(img_file.read()).decode("utf-8")
            webcam_logger.info(
                f"Image at {image_path} successfully converted to base64."
            )
            response = apigateway.post_dict(
                endpoint="image",
                payload_parent_keys={"deviceId": device_id},
                data={"image": base64_string},
            )
            if response.status_code == 200:
                webcam_logger.info("Image successfully sent to API.")
                os.remove(image_path)
                webcam_logger.info(
                    f"Image at {image_path} deleted after successful sending."
                )
            else:
                webcam_logger.error(
                    f"Failed to send image to API. Status code: {response.status_code}"
                )
        except FileNotFoundError:
            webcam_logger.error(
                f"Failed to find image at {image_path} for base64 conversion."
            )

    def release_resources(self):
        """
        Release the webcam and destroy any windows.
        """
        if self.cap is not None:
            self.cap.release()
            cv2.destroyAllWindows()
            webcam_logger.info("Webcam resources released.")


class SerialDevice:
    def __init__(
        self,
        device_name,
        baudrate,
        timeout,
        serial_start,
        serial_end,
        vendor_id=None,
        product_id=None,
    ):
        self.device_name = device_name
        self.logger = setup_custom_logger(device_name)
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_start = serial_start
        self.serial_end = serial_end
        self.port = self.find_port()
        if self.port:
            self.ser = Serial(self.port, self.baudrate, timeout=self.timeout)
            self.logger.info(
                f"Device: {self.device_name} {self.baudrate} {self.timeout}"
            )

    def find_port(self):
        # Function to automatically detect which port to read for the given device.
        potential_ports = self.list_potential_ports()
        self.logger.info(f"Detected potential ports: {potential_ports}")
        for port in potential_ports:
            # Verify port to check for desired signature. If successfully verified, return that port as the correct port.
            if self.verify_port(port):
                self.logger.info(f"Device {self.device_name} found on port: {port}")
                return port
        raise Exception(f"No matching port found for {self.device_name}")

    def list_potential_ports(self):
        # Lists the potential USB ports available, for the system the code is currently running on.
        if platform.system() == "Linux":
            import glob

            return glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        else:
            ports = list(list_ports.comports())
            return [
                port.device
                for port in ports
                if (self.vendor_id is None or port.vid == self.vendor_id)
                and (self.product_id is None or port.pid == self.product_id)
            ]

    def verify_port(self, port):
        try:
            ser = Serial(port, self.baudrate, timeout=self.timeout)

            # Check if port is already open
            if not ser.isOpen():
                ser.open()

            start_time = time.time()

            # Read serial port for 10 seconds
            lines = ""
            while time.time() - start_time < 10:
                line = ser.readline().decode("latin-1").strip()
                lines += line

            # Close the port
            ser.close()

            # Allow port to close before continuing, by sleeping 5 seconds
            time.sleep(5)

            # Check if lines are in data from serial
            if self.serial_start in lines and self.serial_end in lines:
                return True

            else:
                return False
        except Exception as e:
            self.logger.error(f"Error verifying port {port}: {e}")
            return False

    def collect_device_data(self, device, queue):
        # Collect the device data from the serial
        data = {}
        if not device.ser.isOpen():
            device.ser.open()

        # Set initial variables
        reading = True
        collecting = False

        # Read
        while reading:
            line = device.ser.readline().decode("latin-1").strip()
            if device.serial_start in line:
                collecting = True
                data = {}
            if collecting:
                if "checksum" in line.lower():
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    key, value = parts
                    data[key.strip()] = value.strip()

                # If the serial-end signature is recognized, close the port and store the read data in the queue.
                if device.serial_end in line:
                    device.ser.close()
                    reading = False
                    collecting = False
                    queue.put((device.device_name, data))

    @staticmethod
    def send_power_data(file_path):
        try:
            with open(file_path, "r+") as temp_file:
                fcntl.flock(temp_file, fcntl.LOCK_EX)
                temp_data = json.load(temp_file)
                if not temp_data:
                    logger.info("No data to send.")
                    return
                response = apigateway.post_dict(
                    endpoint="power",
                    payload_parent_keys={"deviceId": device_id},
                    data=temp_data,
                )
                if response.status_code == 200:
                    temp_file.seek(0)
                    json.dump([], temp_file, indent=4)
                    temp_file.truncate()
                    logger.info(
                        "Data successfully sent and cleared from temporary storage."
                    )
                else:
                    logger.error(
                        f"Failed to send data, status code: {response.status_code}"
                    )
        except Exception as e:
            logger.error(f"Error sending data: {e}")
