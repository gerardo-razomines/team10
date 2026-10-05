This is the GitHub for team10 of SEED LAB 2026
Mini Project
The camera acts as a user interface for the two wheels. A marker is held in front of the camera, and the quadrant it appears in sets the goal position of each wheel.
Marker quadrant	Left wheel	Right wheel
NE	0	0
NW	0	1
SW	1	1
SE	1	0

Folder layout
vision/ – Raspberry Pi computer vision code
marker_quadrant.py – detects the ArUco marker, finds its quadrant, shows the live camera image with the marker position and goal. Can be run on its own to test the vision subsystem (no Arduino needed).

Hardware
Raspberry Pi 4 with USB webcam
LCD on the Pi and I2C link from Pi to Arduino

How to run the vision test
cd MiniProject/vision
python3 marker_quadrant.py

Press q in the camera window to quit.
