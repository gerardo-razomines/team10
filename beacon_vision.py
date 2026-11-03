#!/usr/bin/env python3
"""
beacon_vision.py
EENG350 Demo 2 - Pi vision loop. This is the program that runs on the robot.

Every camera frame it finds marker 0, measures the bearing (left positive) and distance, reads the
arrow color, and sends one 7-byte packet to the Arduino over I2C (arduino_link.py / I2C_PROTOCOL.md).
It sends a packet on EVERY frame, also when the marker isn't visible - the Arduino waits for those
packets before it starts searching.

Run it:
    IDLE: open this file, press F5.  (settings are in vision_settings.py)
    Terminal:
        python3 beacon_vision.py              normal run (preview window if a monitor is attached)
        python3 beacon_vision.py --dry-run    camera only, nothing sent to the Arduino
        python3 beacon_vision.py --headless   no preview window (this is how the boot service runs it)
Stop with Ctrl+C, or press q in the preview window.
"""
import argparse
import csv
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2

import vision_settings as S
from beacon_detect import ARROW_NAMES, BeaconFinder, Fix, hfov_deg

HERE = Path(__file__).resolve().parent
FT = 0.3048


# ---------------------------------------------------------------- camera
class FrameGrabber:
    """Reads the camera in its own thread and keeps only the NEWEST frame.

    Without this, OpenCV hands back frames that sat in the driver's buffer, so the Pi would report
    where the marker was a few frames ago - wrong while the robot is turning.
    """

    def __init__(self):
        self.cam = cv2.VideoCapture(S.CAMERA_INDEX, cv2.CAP_V4L2)
        if not self.cam.isOpened():
            self.cam = cv2.VideoCapture(S.CAMERA_INDEX)
        if not self.cam.isOpened():
            raise RuntimeError(f"camera {S.CAMERA_INDEX} did not open. Is it plugged in? Try CAMERA_INDEX = 1.")
        self.cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # faster at higher resolutions
        self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, S.FRAME_WIDTH)
        self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, S.FRAME_HEIGHT)
        self.cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cam.set(cv2.CAP_PROP_FPS, 30)
        if S.KEEP_FULL_FRAMERATE:
            self._keep_framerate()
        if S.LOCK_FOCUS is not None:
            self._lock_focus(S.LOCK_FOCUS)
        ok, frame = self.cam.read()
        if not ok:
            raise RuntimeError("camera opened but returned no frame")
        self.height, self.width = frame.shape[:2]
        self.frame, self.count, self.stamp = frame, 1, time.monotonic()
        self.cond = threading.Condition()
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _keep_framerate(self):
        # Webcams on auto-exposure drop to 15 or 7.5 fps in dim light to expose longer.
        # This keeps auto-exposure but stops the frame rate drop (it raises gain instead).
        # The control name depends on the kernel version, so try both. Needs v4l2-ctl (v4l-utils).
        if not shutil.which("v4l2-ctl"):
            print("v4l2-ctl not found (sudo apt install v4l-utils) - can't stop the fps drop in dim light")
            return
        dev = f"/dev/video{S.CAMERA_INDEX}"
        for ctl in ("exposure_dynamic_framerate=0", "exposure_auto_priority=0"):
            subprocess.run(["v4l2-ctl", "-d", dev, "-c", ctl], capture_output=True)

    def _lock_focus(self, value):
        dev = f"/dev/video{S.CAMERA_INDEX}"
        if shutil.which("v4l2-ctl"):
            for ctl in ("focus_automatic_continuous=0", "focus_auto=0", f"focus_absolute={int(value)}"):
                subprocess.run(["v4l2-ctl", "-d", dev, "-c", ctl], capture_output=True)
        self.cam.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        self.cam.set(cv2.CAP_PROP_FOCUS, value)

    def _run(self):
        while self.running:
            ok, frame = self.cam.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self.cond:
                self.frame, self.count, self.stamp = frame, self.count + 1, time.monotonic()
                self.cond.notify_all()

    def next(self, last_count, timeout=1.0):
        """Wait for a frame newer than last_count. Returns (frame, count, stamp) or None."""
        with self.cond:
            if not self.cond.wait_for(lambda: self.count != last_count, timeout):
                return None
            frame, count, stamp = self.frame, self.count, self.stamp
        if S.FLIP_HORIZONTAL and S.FLIP_VERTICAL:
            frame = cv2.flip(frame, -1)
        elif S.FLIP_HORIZONTAL:
            frame = cv2.flip(frame, 1)
        elif S.FLIP_VERTICAL:
            frame = cv2.flip(frame, 0)
        return frame, count, stamp

    def close(self):
        self.running = False
        time.sleep(0.05)
        self.cam.release()


# ---------------------------------------------------------------- Arduino link
class Link:
    """Wraps arduino_link.ArduinoLink so a missing/unplugged Arduino never crashes the vision loop."""

    def __init__(self, enabled):
        self.link, self.why = None, "dry run (SEND_TO_ARDUINO = False or --dry-run)"
        self.sent = self.failed = 0
        if not enabled:
            return
        try:
            from arduino_link import ArduinoLink
            self.link = ArduinoLink(bus=S.I2C_BUS)
            self.why = "I2C"
        except Exception as e:   # no smbus2, I2C disabled, etc.
            self.why = f"I2C not available ({e}) - running as dry run"

    def send(self, fix):
        if self.link is None:
            return None
        ok = self.link.send_fix(fix.seen, fix.angle_deg, fix.dist_m, fix.arrow)
        if ok:
            self.sent += 1
        else:
            self.failed += 1
        return ok

    def status(self):
        return self.link.read_status() if self.link else None

    def close(self):
        if self.link:
            self.link.close()


# ---------------------------------------------------------------- LCD
class Lcd:
    """Optional 16x2 RGB LCD. Updated from its own thread so a slow LCD can't slow the vision loop."""

    def __init__(self):
        self.q = queue.Queue(maxsize=1)
        self.lcd = None
        if not S.USE_LCD:
            return
        try:
            import board
            import busio
            import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd
            self.lcd = character_lcd.Character_LCD_RGB_I2C(busio.I2C(board.SCL, board.SDA),
                                                           S.LCD_COLUMNS, S.LCD_ROWS)
            self.lcd.clear()
            threading.Thread(target=self._run, daemon=True).start()
        except Exception as e:
            print(f"LCD not used ({type(e).__name__}: {e})")
            self.lcd = None

    def show(self, line1, line2, color):
        if self.lcd is None:
            return
        try:
            self.q.get_nowait()
        except queue.Empty:
            pass
        self.q.put_nowait((line1, line2, color))

    def _run(self):
        last = None
        while True:
            item = self.q.get()
            if item == last:
                continue
            last = item
            l1, l2, color = item
            try:
                self.lcd.color = color
                self.lcd.message = l1[:S.LCD_COLUMNS].ljust(S.LCD_COLUMNS) + "\n" + l2[:S.LCD_COLUMNS].ljust(S.LCD_COLUMNS)
            except Exception:
                pass


# ---------------------------------------------------------------- preview drawing
def draw(frame, fix, info):
    if fix.seen:
        pts = fix.corners.astype(int).reshape(-1, 1, 2)
        cv2.polylines(frame, [pts], True, (0, 255, 255), 2)
        if fix.arrow_box:
            x, y, w, h = fix.arrow_box
            col = (0, 200, 0) if fix.arrow == 1 else (0, 0, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), col, 2)
        text = f"ang {fix.angle_deg:+6.2f}  dist {fix.dist_m / FT:4.2f} ft  arrow {ARROW_NAMES[fix.arrow]}"
        col = (0, 255, 0)
    else:
        text, col = "marker 0 not seen", (0, 0, 255)
    h, w = frame.shape[:2]
    cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 0), 1)       # image center = 0 deg
    cv2.putText(frame, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
    cv2.putText(frame, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    cv2.putText(frame, info, (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
    cv2.putText(frame, info, (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame


def want_preview(args):
    if args.headless:
        return False
    if S.SHOW_PREVIEW == "auto":
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return bool(S.SHOW_PREVIEW)


# ---------------------------------------------------------------- main loop
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="don't send anything to the Arduino")
    ap.add_argument("--headless", action="store_true", help="no preview window")
    args = ap.parse_args()

    lcd = Lcd()
    lcd.show("Demo 2 vision", "starting camera", [0, 0, 100])
    # at boot the camera can show up a few seconds after this program starts, so keep trying
    while True:
        try:
            cam = FrameGrabber()
            break
        except RuntimeError as e:
            print(e, "- retrying in 2 s", flush=True)
            lcd.show("Camera not found", "retrying...", [100, 0, 0])
            time.sleep(2)

    finder = BeaconFinder(cam.width, cam.height)
    link = Link(S.SEND_TO_ARDUINO and not args.dry_run)
    preview = want_preview(args)
    print(f"camera {cam.width}x{cam.height}, focal {finder.focal_px:.0f} px [{finder.focal_source}], "
          f"horizontal FOV {hfov_deg(cam.width, finder.focal_px):.0f} deg", flush=True)
    print(f"Arduino link: {link.why}", flush=True)
    print("Arduino SEARCH_STEP_DEG must be smaller than the FOV above.", flush=True)

    log = writer = None
    if S.SAVE_LOG:
        (HERE / "logs").mkdir(exist_ok=True)
        log = open(HERE / "logs" / time.strftime("vision_%Y%m%d_%H%M%S.csv"), "w", newline="")
        writer = csv.writer(log)
        writer.writerow(["t_s", "frame", "seen", "angle_deg", "dist_ft", "arrow", "marker_px",
                         "proc_ms", "sent_ok", "arduino_state", "arduino_turn"])

    t0 = time.monotonic()
    last_count, frames, fps, fps_t, fps_n = 0, 0, 0.0, t0, 0
    next_print = next_status = t0
    status = None
    try:
        while True:
            got = cam.next(last_count)
            if got is None:
                print("no new camera frame for 1 s", flush=True)
                link.send(Fix())   # keep the Arduino fed with 'not seen'
                continue
            frame, last_count, stamp = got
            fix = finder.process(frame)
            ok = link.send(fix)
            now = time.monotonic()
            proc_ms = (now - stamp) * 1000.0
            frames += 1
            fps_n += 1
            if now - fps_t >= 1.0:
                fps, fps_t, fps_n = fps_n / (now - fps_t), now, 0

            if now >= next_status:
                next_status = now + S.STATUS_EVERY_S
                status = link.status()
                state = status[0] if status else ("dry run" if link.link is None else "no reply")
                if fix.seen:
                    l1 = f"{fix.dist_m / FT:4.2f}ft {fix.angle_deg:+5.1f}"
                    l1 += " " + {0: "-", 1: "L", 2: "R"}[fix.arrow]
                    col = [0, 100, 0]
                else:
                    l1, col = "Marker not seen", [100, 0, 0]
                lcd.show(l1, f"{state} {status[1] if status else ''}".strip(), col)

            if writer:
                writer.writerow([f"{now - t0:.3f}", last_count, int(fix.seen), f"{fix.angle_deg:.2f}",
                                 f"{fix.dist_m / FT:.3f}", fix.arrow, f"{fix.marker_px:.1f}",
                                 f"{proc_ms:.1f}", "" if ok is None else int(ok),
                                 status[0] if status else "", status[1] if status else ""])

            if now >= next_print:
                next_print = now + S.PRINT_EVERY_S
                if fix.seen:
                    what = (f"SEEN  angle {fix.angle_deg:+6.2f} deg  dist {fix.dist_m / FT:4.2f} ft "
                            f"({fix.dist_m * 39.37:5.1f} in)  arrow {ARROW_NAMES[fix.arrow]:5s}  "
                            f"marker {fix.marker_px:4.0f} px")
                else:
                    what = "not seen"
                ard = f"  arduino {status[0]}/{status[1]}" if status else ""
                errs = f"  i2c fails {link.failed}" if link.failed else ""
                print(f"{fps:4.1f} fps  {proc_ms:4.0f} ms  {what}{ard}{errs}", flush=True)

            if preview:
                info = f"{fps:4.1f} fps  {proc_ms:3.0f} ms  link: {link.why}"
                cv2.imshow("Demo 2 vision (q to quit)", draw(frame, fix, info))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\nstopped. frames {frames}, packets sent {link.sent}, I2C failures {link.failed}")
        lcd.show("Demo 2 vision", "stopped", [0, 0, 100])
        time.sleep(0.2)
        cam.close()
        link.close()
        if log:
            log.close()
        if preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
