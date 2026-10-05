import cv2

DICT = cv2.aruco.DICT_6X6_50
MIRROR = False

GOALS = {"NE": [0, 0], "NW": [0, 1], "SW": [1, 1], "SE": [1, 0]}

#Set up the ArUco detector
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
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids = find_markers(gray)
    if ids is None:
        return None, None
    #center of the marker is the average of its 4 corners
    x, y = corners[0][0].mean(axis=0)
    h, w = gray.shape

    ns = "N" if y < h / 2 else "S"
    ew = "E" if x > w / 2 else "W"
    return ns + ew, (int(x), int(y))

def draw(frame, quadrant, center, goal):
    h, w = frame.shape[:2]
    cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 255), 1)
    cv2.line(frame, (0, h // 2), (w, h // 2), (255, 255, 255), 1)
    if center:
        cv2.circle(frame, center, 8, (0, 0, 255), -1)
    text = f"{quadrant or 'no marker'} goal: {goal[0]} {goal[1]}"
    cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

def main():
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    goal = [0, 0]
    while True:
        ret, frame = camera.read()
        if not ret:
            print("camera not found")
            break
        if MIRROR:
            frame = cv2.flip(frame, 1)
        quadrant, center = get_quadrant(frame)
        if quadrant and GOALS[quadrant] != goal:
            goal = GOALS[quadrant]
            print("New goal:", goal)
        draw(frame, quadrant, center, goal)
        cv2.imshow("Mini Project", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        
    camera.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
