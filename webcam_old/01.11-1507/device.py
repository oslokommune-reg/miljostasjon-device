import base64
import fcntl
import json
import os
import platform
import time
from datetime import datetime, timezone

import cv2
import numpy as np
from serial import Serial
from tzlocal import get_localzone

from module.aws.apigateway import ApiGatewayConnector
from module.utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)
webcam_logger = setup_custom_logger("webcam")


# Constants for settings
DETECTED_WEBCAM_PORT = 0  # Assuming webcam is at port 0; adjust as needed
MOVEMENT_WAIT_TIME = (
    3  # Time to wait (in seconds) without movement before capturing image
)
TMP_FOLDER = "/tmp"
MOVEMENT_SENSITIVITY_THRESHOLD = (
    500  # Sensitivity for movement detection, lower is more sensitive
)
# Path to JSON files
TEMP_DATA_FILE_PATH = "temporary_device_data.json"

# Get environment variables
apigateway_url = "https://l85dzkg17k.execute-api.eu-west-1.amazonaws.com/dev"
apigateway_key = "sS09t47YoI9pb7KIbX94r2lavXwjbynU3toxkIyn"
device_id = os.getenv("DEVICE_ID", "0x09189b01875")

# Instantiate API Gateway connector
apigateway = ApiGatewayConnector(
    base_url=apigateway_url,
    api_key=apigateway_key,
)


class Webcam:
    def __init__(
        self,
        port=DETECTED_WEBCAM_PORT,
        movement_wait_time=MOVEMENT_WAIT_TIME,
        tmp_folder=TMP_FOLDER,
        movement_sensitivity=MOVEMENT_SENSITIVITY_THRESHOLD,
    ):
        self.port = port
        self.movement_wait_time = movement_wait_time
        self.tmp_folder = tmp_folder
        self.movement_sensitivity = movement_sensitivity
        self.cap = cv2.VideoCapture(self.port)
        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH, 1920
        )  # Set maximum width for high quality
        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT, 1080
        )  # Set maximum height for high quality
        self.cap.set(
            cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"JPEG")
        )  # Set codec for high quality JPEG
        webcam_logger.info(
            f"Webcam initialized with port {self.port}, movement wait time {self.movement_wait_time} seconds, and movement sensitivity {self.movement_sensitivity}."
        )

    def trigger_webcam(self):
        """
        Opens the webcam, checks for movement, captures an image after inactivity,
        ensures the image is not nightvision-only (i.e., has color), and saves it in a tmp folder.
        """
        if not self.cap.isOpened():
            logger.error("Failed to open webcam. Typical.")
            return

        webcam_logger.info("Webcam successfully opened.")

        # Initial setup for movement detection
        ret, prev_frame = self.cap.read()
        if not ret:
            webcam_logger.error("Failed to read from webcam. Seriously?")
            return

        webcam_logger.info("Initial frame read successfully from webcam.")

        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        last_movement_time = time.time()

        while True:
            ret, frame = self.cap.read()
            if not ret:
                webcam_logger.error("Failed to read from webcam. Again?")
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Calculate difference between current frame and previous frame
            frame_diff = cv2.absdiff(prev_gray, gray)
            _, thresh = cv2.threshold(
                frame_diff, self.movement_sensitivity, 255, cv2.THRESH_BINARY
            )
            movement = np.sum(thresh) > 0  # Check if there's significant movement

            if movement:
                last_movement_time = time.time()
                webcam_logger.info("Movement detected, resetting timer.")
            else:
                webcam_logger.info("No movement detected.")
                if time.time() - last_movement_time > self.movement_wait_time:
                    # No movement detected for defined time, capture image
                    webcam_logger.info(
                        "No movement detected for defined time, capturing image."
                    )
                    # if self.is_image_color(frame):
                    image_path = self.save_image(frame)
                    self.send_image_to_api(image_path)
                    break

            prev_gray = gray

        self.cap.release()
        cv2.destroyAllWindows()
        webcam_logger.info("Webcam trigger sequence completed.")

    def is_image_color(self, image):
        """
        Check if the image has colors and is not grayscale or "nightvision-like".
        """
        b, g, r = cv2.split(image)
        # If all channels are equal, the image is grayscale
        if np.array_equal(b, g) and np.array_equal(g, r):
            webcam_logger.info("Image is grayscale. No spooky ghost pictures today.")
            return False
        webcam_logger.info("Image has color. Proceeding.")
        return True

    def save_image(self, image):
        """
        Save the image in a folder for further processing or sending.
        Ensures the directory exists before saving.
        """
        # Ensure the save directory exists
        if not os.path.exists(self.tmp_folder):
            os.makedirs(self.tmp_folder)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(self.tmp_folder, f"webcam_capture_{timestamp}.jpg")
        cv2.imwrite(
            image_path, image, [cv2.IMWRITE_JPEG_QUALITY, 100]
        )  # Save with maximum quality
        webcam_logger.info(f"Image saved to {image_path}.")
        return image_path

    def send_image_to_api(self, image_path):
        """
        Converts the saved image to base64 and sends it to the API.
        """
        try:
            with open(image_path, "rb") as img_file:
                base64_string = base64.b64encode(img_file.read()).decode("utf-8")
            webcam_logger.info(
                f"Image at {image_path} successfully converted to base64."
            )

            # Send data to the API
            webcam_logger.info("Sending image to API.")
            response = apigateway.post_dict(
                endpoint="image",
                payload_parent_keys={"deviceId": device_id},
                data={"image": base64_string},
            )

            if response.status_code == 200:
                webcam_logger.info("Image successfully sent to API.")
                # Optionally delete the image after successful sending
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

        # Detect port
        self.port = self.find_port()

        # Set serial
        if self.port:
            # Instantiate serial with detected port
            self.ser = Serial(self.port, self.baudrate, timeout=self.timeout)

            # Log device config
            self.logger.info(
                f"Device: {self.device_name} {self.baudrate} {self.timeout}"
            )

    def find_port(self):
        potential_ports = self.list_potential_ports()
        self.logger.info(f"Detected potential ports: {potential_ports}")
        for port in potential_ports:
            if self.verify_port(port):
                self.logger.info(f"Device {self.device_name} found on port: {port}")
                return port
        raise Exception(f"No matching port found for {self.device_name}")

    def list_potential_ports(self):
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

    def collect_device_data(device, queue):
        """Collects data from a device and puts it in the queue."""
        data = {}
        # Check if port is already open
        if not device.ser.isOpen():
            device.ser.open()

        reading = True
        collecting = False
        while reading:
            line = device.ser.readline().decode("latin-1").strip()

            if device.serial_start in line:
                collecting = True
                data = {}

            if collecting:
                if "checksum" in line.lower():
                    # Do not collect checksum lines
                    continue

                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    key, value = parts
                    data[key.strip()] = value.strip()

                if device.serial_end in line:
                    # Close
                    device.ser.close()
                    reading = False
                    collecting = False

                    # Add localtime to data
                    device.logger.info(f"Received data block: {data}")
                    queue.put((device.device_name, data))

    def send_power_data():
        """
        Send accumulated data from the temporary JSON file to the API endpoint in the required format.
        """
        try:
            # Read the temporary data file
            with open(TEMP_DATA_FILE_PATH, "r+") as temp_file:
                fcntl.flock(temp_file, fcntl.LOCK_EX)
                temp_data = json.load(temp_file)
                if not temp_data:
                    logger.info("No data to send.")
                    return

                # Send data to the API
                print("api gateway posting..")
                response = apigateway.post_dict(
                    endpoint="power",
                    payload_parent_keys={"deviceId": device_id},
                    data=temp_data,
                )

                # Check if the response status is 200 OK
                if response.status_code == 200:
                    # Clear the data from the temporary file after successful transmission
                    temp_file.seek(0)
                    json.dump([], temp_file, indent=4)
                    temp_file.truncate()

                    logger.info(
                        "Data successfully sent and cleared from temporary storage."
                    )
                else:
                    # Log that data was not successfully sent
                    logger.error(
                        f"Failed to send data, received status code: {response.status_code}. Data retained for next attempt."
                    )

        except Exception as e:
            logger.error(
                f"Error sending data: {e}. Retrying in 5 minutes or until reboot..."
            )
