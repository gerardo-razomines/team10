# this is a checkerboard calibration for this
import argparse
import json
import os
from pathlib import Path
import tempfile
import time

import cv2
import numpy as np
from vision_common import load_config, load_calibration, open_camera, orient_frame


from camera_preview import CameraPreview


# this adds the checkerboard outline and capture count to the camera window
class Preview(CameraPreview):
    def __init__(self):
        super().__init__("Camera Calibration")

    def show(self, frame, pattern, corners, count, target, status):
        if not self.enabled:
            return True
        # make a copy so drawing on the preview doesnt change the actual frame
        canvas = frame.copy()
        if corners is not None:
            cv2.drawChessboardCorners(canvas, pattern, corners, True)
        return super().show(canvas, [f"Views: {count}/{target}", status])


# find the inside corners of the checkerboard in a grayscale image
def find_corners(gray, pattern):
    # SB is more reliable on difficult boards; classic is a compatibility fallback.
    if hasattr(cv2, "findChessboardCornersSB"):
        found, corners = cv2.findChessboardCornersSB(
            gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
        if found:
            return corners.astype(np.float32)
    found, corners = cv2.findChessboardCorners(
        gray, pattern, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not found:
        return None
    # refine the corner positions so they arent just rounded to whole pixels
    return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001))


# FIX: simpler lens model. a cheap webcam has basically no tangential distortion and the k3 term
# just overfits. leaving them free is what let the old calibration move the optical center to
# x=404 (should be near 320), which put a ~6 degree error into every angle we reported.
CALIB_FLAGS = cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K3


def _fit(images, obj, size):
    objects = [obj.copy() for _ in images]
    rms, K, dist, rotations, translations, std_intr, _, per_view = cv2.calibrateCameraExtended(
        objects, images, size, None, None, flags=CALIB_FLAGS)
    return rms, K, dist, std_intr.ravel(), per_view.ravel()


# use all the checkerboard views to estimate the camera settings and lens distortion
def fit_calibration(images, pattern, square_mm, size, max_rms):
    # these are the real checkerboard corner positions, with the square size converted to meters
    obj = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    obj[:, :2] = np.mgrid[:pattern[0], :pattern[1]].T.reshape(-1, 2) * square_mm / 1000
    images = list(images)
    keep = list(range(len(images)))
    rms, K, dist, std, per_view = _fit(images, obj, size)
    # FIX: throw out bad views (blurry, curled paper, misdetected corners) and refit.
    # the old calibration kept a view with 2.7 px error that pulled the whole fit.
    while True:
        limit = max(3 * float(np.median(per_view)), 0.6)
        worst = int(np.argmax(per_view))
        if per_view[worst] <= limit or len(keep) <= 15:
            break
        print(f"dropping view #{keep[worst] + 1} (error {per_view[worst]:.2f} px, limit {limit:.2f} px)", flush=True)
        del images[worst]
        del keep[worst]
        rms, K, dist, std, per_view = _fit(images, obj, size)
    # stop if the fit gives invalid numbers or focal lengths
    if not all(np.isfinite(x).all() for x in (K, dist, rms)) or K[0, 0] <= 0 or K[1, 1] <= 0:
        raise ValueError("this doesnt fit. you need a flat board and more varied tilted views.")
    # a large pixel error means the calibration needs better views
    if rms > max_rms:
        raise ValueError(f"RMS {rms:.3f} px exceeds {max_rms:.3f} px. Images retained; "
                         "remove blurred/bad views, add sharper tilted views, and retry with --images.")
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    w, h = size
    print(f"fx={fx:.1f} (+/-{std[0]:.1f})  fy={fy:.1f}  cx={cx:.1f} (+/-{std[2]:.1f})  "
          f"cy={cy:.1f} (+/-{std[3]:.1f})  k1={dist.ravel()[0]:+.3f} k2={dist.ravel()[1]:+.3f}", flush=True)
    # FIX: sanity checks so a bad calibration can never be saved again.
    # every pixel of error in cx is about 0.075 degrees of angle error at 640 wide.
    problems = []
    if abs(cx - w / 2) > 0.05 * w or abs(cy - h / 2) > 0.08 * h:
        problems.append(f"optical center ({cx:.0f}, {cy:.0f}) is far from the image center ({w/2:.0f}, {h/2:.0f})")
    if abs(fx - fy) > 0.03 * fx:
        problems.append(f"fx and fy differ by {abs(fx - fy):.0f} px (pixels should be square)")
    if std[2] > 4:
        problems.append(f"cx is uncertain by +/-{std[2]:.1f} px (need more tilted views reaching the image edges)")
    corners = np.concatenate([c.reshape(-1, 2) for c in images])
    span_x = (corners[:, 0].max() - corners[:, 0].min()) / w
    span_y = (corners[:, 1].max() - corners[:, 1].min()) / h
    if span_x < 0.8 or span_y < 0.8:
        problems.append(f"board only covered {span_x:.0%} x {span_y:.0%} of the image (move it into the corners)")
    if problems:
        raise ValueError("calibration looks wrong, so it was NOT saved:\n  - " + "\n  - ".join(problems))
    return K, dist, rms, list(per_view), keep


# save to a temporary file first so an interrupted save doesnt replace the good file
def atomic_save(destination, **values):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=destination.parent, suffix=".npz")
    try:
        with os.fdopen(fd, "wb") as stream:
            np.savez(stream, **values)
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    # these are the options you can change when running calibration from the terminal
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(Path(__file__).with_name("camera_config.json")))
    ap.add_argument("--cols", type=int, default=9, help="INNER corners across (10 squares = 9)")
    ap.add_argument("--rows", type=int, default=6, help="INNER corners down (7 squares = 6)")
    ap.add_argument("--square-mm", type=float, default=20)
    ap.add_argument("--views", type=int, default=25, help="target live views (minimum 15)")
    ap.add_argument("--seconds", type=float, default=300, help="maximum live capture time")
    ap.add_argument("--images", type=Path, help="fit saved PNG/JPG images instead of opening camera")
    ap.add_argument("--max-rms", type=float, default=1.0)
    ap.add_argument("--force", action="store_true", help="explicitly replace existing calibration after a good fit")
    ap.add_argument("--no-preview", action="store_true", help="disable live display for remote/headless use")
    args = ap.parse_args()
    # check the inputs before opening the camera or trying to fit anything
    if args.cols < 3 or args.rows < 3 or args.views < 15:
        ap.error("Use at least 3 x 3 inner corners and at least 15 views.")
    if any(not np.isfinite(v) or v <= 0 for v in (args.square_mm, args.seconds, args.max_rms)):
        ap.error("Square size, seconds, and max-rms must be finite and positive.")
    cfg = load_config(args.config)
    destination = Path(cfg["calibration_file"])
    # if theres already a compatible calibration, just use that unless force was requested
    if destination.exists() and not args.force:
        load_calibration(destination, cfg)
        print(f"its using a  saved calibration: {destination}\n so no calibration needed. run marker_angle.py. "
              "us --force  to recalibrate.")
        return
    # count the inside corners here, not the number of squares
    pattern = (args.cols, args.rows)
    focus = cfg.get("focus")
    size = (cfg["width"], cfg["height"])
    images = []
    sources = []
    # this lets us retry calibration using pictures that were already saved
    if args.images:
        paths = sorted(p for p in args.images.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        for path in paths:
            frame = cv2.imread(str(path))
            if frame is None:
                print(f"skipp unreadable image: {path.name}")
                continue
            if (frame.shape[1], frame.shape[0]) != size:
                raise ValueError(f"{path.name}: expected {size}; update config to match the demo resolution.")
            # Saved captures already have orient_frame applied. External images must match that orientation.
            corners = find_corners(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), pattern)
            print(f"{path.name}: {'board detected' if corners is not None else 'board NOT found'}", flush=True)
            if corners is not None:
                images.append(corners)
                sources.append(str(path.resolve()))
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # keep the captured views in their own folder in case we need them later
        folder = Path(tempfile.mkdtemp(prefix="calibration_views_", dir=destination.parent))
        (folder / "capture_settings.json").write_text(json.dumps(
            {**cfg, "cols": args.cols, "rows": args.rows, "square_mm": args.square_mm}, indent=2))
        print(f"Captures: {folder}\nShow the ENTIRE {args.cols+1} x {args.rows+1}-square board. "
              "Move slowly to left/right/top/bottom; vary distance and tilt. Ctrl+C fits collected views.", flush=True)
        preview = None if args.no_preview else Preview()
        try:
            cam = open_camera(cfg)
            # read back the focus value actually in use (negative = camera has no focus control)
            focus = cam.get(cv2.CAP_PROP_FOCUS)
            focus = float(focus) if focus >= 0 else None
            print("autofocus is OFF; focus value locked at " +
                  (f"{focus:g}" if focus is not None else "(camera has no focus control)"), flush=True)
        except Exception:
            if preview is not None:
                preview.close()
            raise
        # use elapsed time so changes to the system clock dont affect the capture timer
        start = time.monotonic()
        next_capture = start + 2  # allow exposure to settle
        next_status = start
        failures = 0
        corners = None
        status = "Camera warming up..."
        next_detection = start + 2
        previous = None
        try:
            while len(images) < args.views and time.monotonic() - start < args.seconds:
                ok, raw = cam.read()
                # skip occasional failed frames, but stop if the camera keeps failing
                if not ok:
                    failures += 1
                    if failures >= 30:
                        raise RuntimeError("camera returned no frames 30 times so check USB/camera_index.")
                    time.sleep(0.05)
                    continue
                failures = 0
                # use the same image direction here as in the mrker demo
                frame = orient_frame(raw, cfg)
                if (frame.shape[1], frame.shape[0]) != size:
                    raise ValueError(f"camera delivered {(frame.shape[1], frame.shape[0])}, expected {size}. "
                                     "set the width/height in camera_config.json to a resolution thats right.")
                now = time.monotonic()
                if now >= next_detection:
                    corners = find_corners(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), pattern)
                    # space out the corner searches so the preview can keep updating
                    next_detection = time.monotonic() + 0.25
                    # FIX: only save when the board is being held still, so we dont save motion-blurred views
                    still = (corners is not None and previous is not None and
                             float(np.sqrt(np.mean((corners - previous)**2))) < 1.0)
                    previous = corners
                    # only save a view if its different enough from every view already collected
                    moved = corners is not None and all(
                        float(np.sqrt(np.mean((corners - old)**2))) > 12 for old in images)
                    # leave a little time between captures so we can move the board to a new positon
                    if moved and still and now >= next_capture:
                        path = folder / f"view_{len(images)+1:03d}.png"
                        if not cv2.imwrite(str(path), frame):
                            raise OSError(f"cant save capture: {path}")
                        images.append(corners.copy())
                        sources.append(str(path.resolve()))
                        status = "view was saved change board position and tilt."
                        print(f"saved view {len(images)}/{args.views}. change the board position and tilt.", flush=True)
                        next_capture = time.monotonic() + 1.2
                    else:
                        status = ("Board wasnt found so show the whole board clearly."
                                  if corners is None else
                                  "hold the board STILL..." if moved and not still else
                                  "the board was found. move it to a new spot / tilt it.")
                        if now >= next_status:
                            print(status, flush=True)
                            next_status = now + 3
                if preview is not None and not preview.show(
                        frame, pattern, corners, len(images), args.views, status):
                    print("preview closed. fitting collected views...", flush=True)
                    break
        # ctrl+c stops capture and tries fitting the views we have so far
        except KeyboardInterrupt:
            print("\n fitting collected views...", flush=True)
        finally:
            # give the camera back when capture finishes, including if theres an error
            cam.release()
            if preview is not None:
                preview.close()
    # dont save a calibration if there werent enough usable checkerboard views
    if len(images) < 15:
        raise ValueError(f"only {len(images)} usable views and you need at least 15. captures are kept. "
                         "retry capture or use --images FOLDER with additional views.")
    K, dist, rms, errors, keep = fit_calibration(images, pattern, args.square_mm, size, args.max_rms)
    sources = [sources[i] for i in keep]
    # save the fit plus the camera settings so the demo can check that they still match
    atomic_save(destination, camera_matrix=K, dist_coeffs=dist, image_size=np.array(size),
        unmirror_input=np.array(cfg["unmirror_input"]), camera_index=np.array(str(cfg["camera_index"])),
        rms=np.array(rms), per_view_rms=np.array(errors), views=np.array(len(sources)),
        focus=np.array(np.nan if focus is None else focus),
        source_images=np.array(sources))
    print(f"saved {destination}\nViews: {len(images)}; RMS: {rms:.3f} px. "
          "future demos load this file without recalibrating.\n"
          "NEXT: run verify_angle.py to check the angles against a tape measure.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, cv2.error) as exc:
        raise SystemExit(f"Calibration: {exc}")
