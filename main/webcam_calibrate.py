import cv2
import numpy as np


def nothing(x):
    pass


# Initialize the video capture
cap = cv2.VideoCapture(0)
# Create a window for the calibration
cv2.namedWindow("Calibration")

# Create trackbars for threshold adjustment
cv2.createTrackbar("Threshold", "Calibration", 25, 255, nothing)

# Read the first frame and set up the average
ret, frame = cap.read()
if not ret:
    print("Failed to capture from webcam")
    exit()

average_frame = np.float32(frame)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Apply running average to update the background model
    cv2.accumulateWeighted(frame, average_frame, 0.01)
    background = cv2.convertScaleAbs(average_frame)

    # Calculate the difference between current frame and background
    frame_diff = cv2.absdiff(frame, background)

    # Convert difference to grayscale
    gray_diff = cv2.cvtColor(frame_diff, cv2.COLOR_BGR2GRAY)

    # Get current threshold value from the trackbar
    threshold_value = cv2.getTrackbarPos("Threshold", "Calibration")

    # Apply threshold to detect movement
    _, thresh = cv2.threshold(gray_diff, threshold_value, 255, cv2.THRESH_BINARY)

    # Display the frames to help visualize calibration
    cv2.imshow("Frame", frame)
    cv2.imshow("Background", background)
    cv2.imshow("Thresholded Difference", thresh)

    # Exit loop when 'q' is pressed
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
