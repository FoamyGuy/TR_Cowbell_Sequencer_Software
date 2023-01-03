import board
import digitalio
import storage

up_btn = digitalio.DigitalInOut(board.GP21)



up_btn.direction = digitalio.Direction.INPUT
up_btn.pull = digitalio.Pull.UP

storage.remount("/", not up_btn.value)