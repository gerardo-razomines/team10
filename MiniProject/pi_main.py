import queue
import threading

import cv2
import board
import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd
from smbus2 import SMBus

from marker_quadrant import get_quadrant, draw, GOALS, MIRROR

ARD_ADDR = 8
q = queue.Queue()


def i2c_worker():
    """thread sends each new goal to the Arduino then updates the LCD"""
    lcd = character_lcd.Character_LCD_RGB_I2C(board.I2C(), 16, 2)
    lcd.color = [0, 100, 0]
    arduino = SMBus(1)

    while True:
        goal = q.get()            #waits until a new goal
        while not q.empty():      #skip to the newest one
            goal = q.get()

        try:
            arduino.write_byte(ARD_ADDR, goal[0] * 2 + goal[1])
        except OSError:
            print("Arduino not responding")

        lcd.clear()
        lcd.message = f"Goal Position:\n{goal[0]} {goal[1]}"


def main():
    #daemon=True means the thread stops
    threading.Thread(target=i2c_worker, daemon=True).start()

    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    goal = [0, 0]
    q.put(goal)

    while True:
        ret, frame = camera.read()
        if not ret:
            print("Camera not found")
            break
        if MIRROR:
            frame = cv2.flip(frame, 1)

        quadrant, center = get_quadrant(frame)

        #Only send when the goal changes
        if quadrant and GOALS[quadrant] != goal:
            goal = GOALS[quadrant]
            print("New goal:", goal)
            q.put(goal)

        draw(frame, quadrant, center, goal)
        cv2.imshow("Mini Project", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
