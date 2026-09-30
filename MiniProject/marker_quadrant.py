"""
marker_quadrant.py
EENG350 Mini Project - Computer Vision subsystem
Purpose:
Finds an ArUco marker in the camera image, figures out which quadrant
(NE, NW, SW, SE) it is in, and turns that into the wheel goal positions.
Quadrant -> [Left, Right]
NE -> [0, 0]
NW -> [0, 1]
SW -> [1, 1]
SE -> [1, 0]
(Left wheel: north = 0, south = 1. Right wheel: east = 0, west = 1.)
Hardware:
USB webcam plugged into any USB port on the Raspberry Pi.
How to run:
python3 marker_quadrant.py (press q in the camera window to quit)
"""
import cv2
DICT = cv2.aruco.DICT_6X6_50 # must match the marker you printed
MIRROR = False # set True if left/right look swapped
Quadrant name -> [left wheel, right wheel]
GOALS = {"NE": [0, 0], "NW": [0, 1], "SW": [1, 1], "SE": [1, 0]}
Set up the ArUco detector (works on both old and new OpenCV versions)
aruco_dict = cv2.aruco.getPredefinedDictionary(DICT)
try:
detector = cv2.aruco.ArucoDetector(aruco_dict, cv2.aruco.DetectorParameters())
def find_markers(gray):
corners, ids, _ = detector.detectMarkers(gray)
return corners, ids
except AttributeError:
params = cv2.aruco.DetectorParameters_create()
def find_markers(gray):
corners, ids, _ = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=params)
return corners, ids

def get_quadrant(frame):
"""Returns (quadrant, (x, y)) of the first marker found, or (None, None)."""
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
corners, ids = find_markers(gray)
if ids is None:
return None, None
# Center of the marker = average of its 4 corners
x, y = corners[0][0].mean(axis=0)
h, w = gray.shape
ns = "N" if y < h / 2 else "S" # top half = north (y goes DOWN in images)
ew = "E" if x > w / 2 else "W" # right half = east
return ns + ew, (int(x), int(y))

def draw(frame, quadrant, center, goal):
"""Draws the crosshair, a dot on the marker, and the goal text."""
h, w = frame.shape[:2]
cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 255), 1)
cv2.line(frame, (0, h // 2), (w, h // 2), (255, 255, 255), 1)
if center:
cv2.circle(frame, center, 8, (0, 0, 255), -1)
text = f"{quadrant or 'No marker'} Goal: {goal[0]} {goal[1]}"
cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

def main():
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640) # small frames = faster detection
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
goal = [0, 0] # system starts with both wheels at 0
while True:
ret, frame = camera.read()
if not ret:
print("Camera not found. Is it plugged in?")
break
if MIRROR:
frame = cv2.flip(frame, 1)
quadrant, center = get_quadrant(frame)
# Only react when the goal actually changes (keeps the LCD/Arduino from lagging later)
if quadrant and GOALS[quadrant] != goal:
goal = GOALS[quadrant]
print("New goal:", goal) # NEXT STEP: send to LCD + Arduino here
draw(frame, quadrant, center, goal)
cv2.imshow("Mini Project", frame)
if cv2.waitKey(1) & 0xFF == ord("q"):
break
camera.release()
cv2.destroyAllWindows()

if __name__ == "__main__":
main()
