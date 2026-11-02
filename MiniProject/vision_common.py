# this is vision common
# these camera utilities that are shared by calibration and the marker-angle demonstration
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np


def load_config(path):
    # read the shared camera settings from the requested file
    path = Path(path).resolve()
    cfg = json.loads(path.read_text())
    # check the image dimensions and frame rate before opening the camera
    for name in ("width", "height", "fps"):
        if not isinstance(cfg[name], int) or cfg[name] <= 0:
            raise ValueError(f"{name} has to be a positive integer")
    if not isinstance(cfg["unmirror_input"], bool):
        raise ValueError("unmirror_input must be true or false")
    # FIX: constant trim found with verify_angle.py (camera mounted slightly crooked, etc.)
    cfg.setdefault("angle_offset_deg", 0.0)
    cfg.setdefault("focus", None)
    # a relative calibration path starts from the settings file folder
    calibration = Path(cfg["calibration_file"])
    cfg["calibration_file"] = str(calibration if calibration.is_absolute() else path.parent/calibration)
    return cfg


def lock_focus(cam, cfg, focus=None):
    # FIX: autofocus changes the focal length of the lens, which silently breaks the calibration
    # (our two old calibration sessions disagreed by ~20% in focal length because of this).
    # so we turn autofocus off and, if we know the focus value used at calibration, we set it back.
    # cameras with a fixed-focus lens just ignore all of this, which is fine.
    device = f"/dev/video{cfg['camera_index']}"
    if shutil.which("v4l2-ctl"):
        # the control name depends on the kernel version, so try both
        for control in ("focus_automatic_continuous=0", "focus_auto=0"):
            subprocess.run(["v4l2-ctl", "-d", device, "-c", control], capture_output=True)
        if focus is not None:
            subprocess.run(["v4l2-ctl", "-d", device, "-c", f"focus_absolute={int(round(focus))}"],
                           capture_output=True)
    # also ask through opencv in case v4l2-ctl isnt installed
    cam.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    if focus is not None:
        cam.set(cv2.CAP_PROP_FOCUS, focus)
    # report the focus value that is actually in use (negative means the camera has no focus control)
    value = cam.get(cv2.CAP_PROP_FOCUS)
    return float(value) if np.isfinite(value) and value >= 0 else None


def open_camera(cfg, focus=None):
    # open the configured camera and check that its actually available
    cam = cv2.VideoCapture(cfg["camera_index"])
    if not cam.isOpened():
        cam.release()
        raise RuntimeError("cant open the USB camera, you need to check camera_index and USB connection")
    # request the image size and frame rate from the settings
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["width"])
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["height"])
    cam.set(cv2.CAP_PROP_FPS, cfg["fps"])
    # request a small buffer so we arent measuring angles from older frames
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    # use the focus from the config file if one is set there, otherwise the one saved at calibration
    if cfg.get("focus") is not None:
        focus = cfg["focus"]
    lock_focus(cam, cfg, focus)
    # throw away the first frames while exposure and focus settle
    for _ in range(15):
        cam.read()
    return cam


def saved_focus(path):
    # the focus value that was locked when the calibration was taken (None if unknown)
    try:
        with np.load(path, allow_pickle=False) as saved:
            if "focus" in saved.files:
                value = float(saved["focus"])
                return value if np.isfinite(value) else None
    except (OSError, ValueError):
        pass
    return None


def orient_frame(frame, cfg):
    # this sets true only if the camera driver outputs horizontally mirrored pixels
    # the smae value needs to be used during the calibration and the demo
    return cv2.flip(frame, 1) if cfg["unmirror_input"] else frame


def detector(dictionary_name):
    # marker detection needs the opencv build that includes aruco
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("openCV doesnt have aruco. you need to install opencv-contrib-python")
    if dictionary_name not in ("DICT_6X6_50", "DICT_6X6_100", "DICT_6X6_250", "DICT_6X6_1000"):
        raise ValueError("the demo needs a standard 6x6 dictionary")
    # use the same marker dictionary that the printed markers came from
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary_name))
    # newer and older opencv versions create the detector a little differently
    if hasattr(cv2.aruco, "ArucoDetector"):
        params = cv2.aruco.DetectorParameters()
        # refine the corner locations for a more precise angle measurement
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        return cv2.aruco.ArucoDetector(dictionary, params).detectMarkers
    params = cv2.aruco.DetectorParameters_create()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return lambda gray: cv2.aruco.detectMarkers(gray, dictionary, parameters=params)


def load_calibration(path, cfg):
    if not Path(path).is_file():
        raise FileNotFoundError("No saved camera calibration. Run python3 calibrate_camera.py once first.")
    # load the saved camera matrix, distortion, resolution, and image direction
    with np.load(path, allow_pickle=False) as saved:
        K = np.asarray(saved["camera_matrix"], dtype=np.float64)
        dist = np.asarray(saved["dist_coeffs"], dtype=np.float64)
        size = tuple(int(x) for x in saved["image_size"])
        mirrored = bool(saved["unmirror_input"].item())
        if "camera_index" in saved and str(saved["camera_index"].item()) != str(cfg["camera_index"]):
            raise ValueError("camera index changed. Restore it or calibrate the new camera with --force.")
    # check that the saved matrix and distortion values are usable
    if K.shape != (3, 3) or K[0, 0] <= 0 or K[1, 1] <= 0:
        raise ValueError("the calibration camera matrix isnt valid")
    if dist.size not in (4, 5, 8, 12, 14) or not np.isfinite(K).all() or not np.isfinite(dist).all():
        raise ValueError("the calibration values arent finite")
    # the demo needs the same resolution that was used for calibration
    if size != (cfg["width"], cfg["height"]):
        raise ValueError("the calibration resolution is different from camera_config.json, you need to recalibrate")
    # flipping the image differently would make the saved calibration inconsistent
    if mirrored != cfg["unmirror_input"]:
        raise ValueError("the image orientation has changed since calibration, you need to recalibrate")
    return K, dist, size


def marker_bearing(corners, K, dist):
    # the horizontal bearing of the marker CENTER in degrees and positive to camera left
    # you need to undistort all the corners before you find the diagonal intersection
    # the mean of the four distorted corners isnt a projeted image of the physical marker center
    # theres no marker size or pose/orientation angle thats needed for the bearing

    pts = cv2.undistortPoints(np.asarray(corners, dtype=np.float64).reshape(4, 1, 2), K, dist).reshape(4, 2)
    # add a third coordinate so we can intersect the marker diagonals
    hom = np.column_stack((pts, np.ones(4)))
    # the diagonal intersection gives the projected center of the physical marker
    center = np.cross(np.cross(hom[0], hom[2]), np.cross(hom[1], hom[3]))
    # stop if the corners dont give a valid center
    if not np.isfinite(center).all() or abs(center[2]) < 1e-12:
        raise ValueError("the marker corners are degenerate")
    # divide back to normalized image coordinates before finding the angle
    ray = center[:2]/center[2]
    # the minus sign makes angles to the camera left positive, and this returns degrees
    return float(np.degrees(np.arctan2(-ray[0], 1.0)))


def measured_angle(corners, K, dist, cfg):
    # the angle we actually report: the calibrated bearing minus the constant trim from verify_angle.py
    return marker_bearing(corners, K, dist) - cfg["angle_offset_deg"]


class AngleFilter:
    # FIX: single frames jitter by a few hundredths to tenths of a degree, and the marker is
    # sitting still during the test, so we report the median of the last several frames.
    # if the marker moves (big jump) or disappears we start over so we never show a stale angle.
    def __init__(self, frames=15, jump_deg=1.5):
        self.frames = frames
        self.jump_deg = jump_deg
        self.values = []

    def reset(self):
        self.values = []

    def add(self, angle):
        if self.values and abs(angle - float(np.median(self.values))) > self.jump_deg:
            self.values = []
        self.values.append(angle)
        self.values = self.values[-self.frames:]
        return float(np.median(self.values))
