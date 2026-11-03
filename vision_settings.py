# vision_settings.py
# EENG350 Demo 2 - every setting the Pi vision code uses, in one place.
# Edit the numbers here, save, and re-run. Nothing else needs to change.

# ===================== Camera =====================
CAMERA_INDEX = 0            # /dev/video0. Try 1 if the camera won't open.
FRAME_WIDTH = 640           # same webcam mode as Demo 1. If the marker isn't found at 6 ft,
FRAME_HEIGHT = 480          # try 1280 x 720 and re-run quick_focal.py (the focal length changes).
FLIP_HORIZONTAL = False     # True if the preview looks mirrored (text on a sign reads backwards)
FLIP_VERTICAL = False       # True if the camera is mounted upside down (set BOTH flips True for that)
KEEP_FULL_FRAMERATE = True # stop the webcam dropping to 7.5 fps in dim light (needs v4l2-ctl)
LOCK_FOCUS = None          # None = leave the camera alone. A number (e.g. 30) = autofocus off, fixed focus.

# ===================== Focal length (no checkerboard needed) =====================
# Angle and distance both come from the focal length in pixels.
# - quick_focal.py measures it with ONE tape-measure reading and saves it to camera_focal.json,
#   which overrides the value below.
# - Without that file we use FOCAL_PX_DEFAULT. Our Demo 1 calibrations gave roughly 710-930 px
#   at 640 x 480, so 770 is a middle guess. A 10% error here is a 10% distance error.
FOCAL_PX_DEFAULT = 770.0
FOCAL_FILE = "camera_focal.json"

# ===================== Marker =====================
MARKER_ID = 0               # 6x6 dictionary, ID 0 (from the Demo 2 instructions)
MARKER_SIZE_M = 0.0508      # 2.0 inches, the black square only. Measure your print!
                            # If it isn't exactly 2.00 in, put the real size here (in * 0.0254).

# ===================== Arrow (color next to the marker) =====================
# Green arrow LEFT of the marker = turn left. Red arrow RIGHT of the marker = turn right.
# HSV ranges in OpenCV units: H 0-180, S 0-255, V 0-255.
GREEN_H = (40, 95)
GREEN_S_MIN = 70
GREEN_V_MIN = 40
RED_H_LOW = 10              # red wraps around: H <= RED_H_LOW or H >= RED_H_HIGH
RED_H_HIGH = 165
RED_S_MIN = 90
RED_V_MIN = 50
ARROW_MIN_AREA = 0.05       # blob area as a fraction of the marker's area (the real arrow is ~0.2)
ARROW_MAX_AREA = 0.80

# ===================== Arduino link =====================
SEND_TO_ARDUINO = True      # False = camera only, prints what it would send (no Arduino needed)
I2C_BUS = 1
STATUS_EVERY_S = 0.25       # how often to read the Arduino's state byte back (for the LCD/console)

# ===================== LCD (optional) =====================
USE_LCD = True              # Adafruit 16x2 RGB LCD plate. Skipped automatically if it isn't found.
LCD_COLUMNS = 16
LCD_ROWS = 2

# ===================== Logging / preview =====================
SHOW_PREVIEW = "auto"       # "auto" = show a window if a monitor is attached, True / False to force it
SAVE_LOG = True             # writes logs/vision_<time>.csv: one line per frame, for after a run
PRINT_EVERY_S = 0.5         # console print rate
