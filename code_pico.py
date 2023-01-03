# DJDevon3 TR-Cowbell Hardware Test
# 2022/11/09 - Neradoc & DJDevon3
# Based on PicoStepSeq by @todbot Tod Kurt
# https://github.com/todbot/picostepseq/
import asyncio
import json
import struct
import time
from io import BytesIO

import board
import busio
import msgpack
from digitalio import Direction
from adafruit_mcp230xx.mcp23017 import MCP23017
from mcp23017_scanner import McpKeysScanner
from multi_macropad import MultiKeypad
from adafruit_midi.note_off import NoteOff
from adafruit_midi.note_on import NoteOn
import adafruit_midi
import usb_midi
import rotaryio
import board
import digitalio
from adafruit_debouncer import Debouncer, Button
#from saved_loops import SAVED_LOOPS
import storage


print(f"Storage is readonly: {storage.getmount('/').readonly}")
display_uart = busio.UART(board.GP0, board.GP1, baudrate=19200)

encoder = rotaryio.IncrementalEncoder(board.GP18, board.GP19)

encoder_btn_pin = digitalio.DigitalInOut(board.GP20)
encoder_btn_pin.direction = digitalio.Direction.INPUT
encoder_btn_pin.pull = digitalio.Pull.UP
encoder_btn = Debouncer(encoder_btn_pin)

up_btn_pin = digitalio.DigitalInOut(board.GP21)
up_btn_pin.direction = digitalio.Direction.INPUT
up_btn_pin.pull = digitalio.Pull.UP
up_btn = Button(up_btn_pin)

down_btn_pin = digitalio.DigitalInOut(board.GP28)
down_btn_pin.direction = digitalio.Direction.INPUT
down_btn_pin.pull = digitalio.Pull.UP
down_btn = Button(down_btn_pin)

right_btn_pin = digitalio.DigitalInOut(board.GP22)
right_btn_pin.direction = digitalio.Direction.INPUT
right_btn_pin.pull = digitalio.Pull.UP
right_btn = Button(right_btn_pin)

left_btn_pin = digitalio.DigitalInOut(board.GP15)
left_btn_pin.direction = digitalio.Direction.INPUT
left_btn_pin.pull = digitalio.Pull.UP
left_btn = Button(left_btn_pin)

middle_btn_pin = digitalio.DigitalInOut(board.GP14)
middle_btn_pin.direction = digitalio.Direction.INPUT
middle_btn_pin.pull = digitalio.Pull.UP
middle_btn = Button(middle_btn_pin)

# Initialize 2 Separate Physical I2C busses
i2c0 = busio.I2C(board.GP13, board.GP12)  # Bus I2C0
i2c1 = busio.I2C(board.GP11, board.GP10)  # Bus I2C1

# Initialize MCP Chip 1 Step Switches 0-7
mcp1 = MCP23017(i2c0, address=0x20)
# Initalize MCP Chip 2 Step Switches 8-15
mcp2 = MCP23017(i2c1, address=0x20)

PINS1 = [0, 1, 2, 3, 4, 5, 6, 7]
PINS2 = [0, 1, 2, 3, 4, 5, 6, 7]

# MCP scanner and multikeypad
scanner1 = McpKeysScanner(mcp1, PINS1)
scanner2 = McpKeysScanner(mcp2, PINS2)
all_scanner = MultiKeypad(scanner1, scanner2)

# LED pins on ports B
mcp1_led_pins = [mcp1.get_pin(pin) for pin in range(8, 16)]
mcp2_led_pins = [mcp2.get_pin(pin) for pin in range(8, 16)]

# all the LED pins organized per MCP chip
led_pins_per_chip = (mcp1_led_pins, mcp2_led_pins)

# ordered list of led coordinates
led_pins = [(a, b) for a in range(2) for b in range(8)]

# Set all LED pins to output
for (m, x) in led_pins:
    led_pins_per_chip[m][x].direction = Direction.OUTPUT


# status of the button latches
# latches = [False] * 16
#
# notes = [None] * 16
#
# SELECTED_INDEX = -1

class State:
    def __init__(self, saved_state_json=None):
        self.selected_index = -1
        self.notes = [0] * 16
        self.latches = [False] * 16
        self.last_position = encoder.position
        self.mode = "selecting_index"
        self.send_off = True
        self.received_ack = True
        self.selected_file = None
        self.saved_loops = None

        if saved_state_json:
            saved_state_obj = json.loads(saved_state_json)
            for i, note in enumerate(saved_state_obj["notes"]):
                self.notes[i] = note
                if note != 0:
                    self.latches[i] = True
            self.selected_index = saved_state_obj['selected_index']


    def load_state_json(self, saved_state_json):

        saved_state_obj = json.loads(saved_state_json)
        self.load_state_obj(saved_state_obj)

    def load_state_obj(self, saved_state_obj):
        self.notes = saved_state_obj['notes']
        self.selected_index = saved_state_obj['selected_index']
        for i, note in enumerate(self.notes):
            if note != 0:
                self.latches[i] = True
            else:
                self.latches[i] = False


def increment_selected(state):
    _checked = 0
    _checking_index = (state.selected_index + 1) % 16
    while _checked < 16:
        if state.notes[_checking_index] is not 0:
            state.selected_index = _checking_index
            break
        else:
            _checked += 1
            _checking_index = (_checking_index + 1) % 16

    if _checked >= 16:
        state.selected_index = -1


def decrement_selected(state):
    _checked = 0
    _checking_index = (state.selected_index - 1) % 16
    while _checked < 16:
        if state.notes[_checking_index] is not 0:
            state.selected_index = _checking_index
            break
        else:
            _checked += 1
            _checking_index = (_checking_index - 1) % 16

    if _checked >= 16:
        state.selected_index = -1


def toggle_latch(mcp, pin, state):
    # print(mcp, pin)

    state.latches[mcp * 8 + pin] = not state.latches[mcp * 8 + pin]
    if state.latches[mcp * 8 + pin]:
        state.selected_index = mcp * 8 + pin
        state.notes[mcp * 8 + pin] = 60
    else:
        state.notes[mcp * 8 + pin] = 0


def get_latch(mcp, pin, state):
    return state.latches[mcp * 8 + pin]


# NOTE: it is assumed that key number x (port A) on MCP number y matches
# the LED numnber x (port B) on the same MCP number y
# if not, a conversion function could be used to translate:
# (key_x, key_y) -> (led_x, led_y)

# midi setup
# midi_tx_pin, midi_rx_pin = board.GP16, board.GP17
# midi_timeout = 0.01
# uart = busio.UART(tx=midi_tx_pin, rx=midi_rx_pin,
#                   baudrate=31250, timeout=midi_timeout)

midi = adafruit_midi.MIDI(
    midi_out=usb_midi.ports[1], out_channel=1
)


async def play_note(note, delay, state):
    if (note != 0):
        if not state.send_off:
            midi.send(NoteOff(note, 0))
        if note == 61:

            note_on = NoteOn(note, 127)
            print(f"playing other channel? {note_on.channel}")
            midi.send(note_on, channel=2)
            await asyncio.sleep(delay)

            if state.send_off:
                midi.send(NoteOff(note, 0), channel=2)
        else:
            note_on = NoteOn(note, 127)
            midi.send(note_on)

            await asyncio.sleep(delay)

            if state.send_off:
                midi.send(NoteOff(note, 0))


def index_to_chip_and_index(index):
    return index // 8, index % 8


def chip_and_index_to_index(chip, index):
    return chip * 8 + index


async def blink_the_leds(state, delay=0.125):
    while True:
        # print(state.notes)
        # print(state.selected_index)
        # blink all the LEDs together
        for (x, y) in led_pins:
            if not get_latch(x, y, state):
                led_pins_per_chip[x][y].value = True
                # time.sleep(0.001)
                await asyncio.sleep(0.001)
                led_pins_per_chip[x][y].value = False
                await asyncio.sleep(delay)
            else:
                # print("getlatch was true")
                # print(f"index: {x}, {y} - {x * 8 + y}")
                led_pins_per_chip[x][y].value = False
                await play_note(state.notes[x * 8 + y], delay, state)
                # time.sleep(0.001)
                led_pins_per_chip[x][y].value = True


async def blink_selected(state, delay=0.05):
    while True:
        if state.selected_index >= 0:
            _selected_chip_and_index = index_to_chip_and_index(state.selected_index)
            # print(led_pins_per_chip[_selected_chip_and_index[0]][_selected_chip_and_index[1]].value)
            if state.notes[state.selected_index] is not None:
                led_pins_per_chip[_selected_chip_and_index[0]][_selected_chip_and_index[1]].value = False
                # time.sleep(delay)
                await asyncio.sleep(delay)
                led_pins_per_chip[_selected_chip_and_index[0]][_selected_chip_and_index[1]].value = True

            else:
                if led_pins_per_chip[_selected_chip_and_index[0]][_selected_chip_and_index[1]].value:
                    led_pins_per_chip[_selected_chip_and_index[0]][_selected_chip_and_index[1]].value = False
                await asyncio.sleep(delay)
        else:
            for i in range(16):
                chip_num, index = index_to_chip_and_index(i)
                led_pins_per_chip[chip_num][index].value = False
            await asyncio.sleep(delay)


async def read_buttons(state):
    while True:
        # scan the buttons
        scanner1.update()
        scanner2.update()
        # treat the events
        while event := all_scanner.next_event():
            mcp_number = event.pad_number
            key_number = event.key_number
            if event.pressed:

                print(f"Key pressed : {mcp_number} / {key_number}")
                # key pressed, find the matching LED
                led_pin = led_pins_per_chip[mcp_number][key_number]
                # invert the latch value (independently of the LED)
                toggle_latch(mcp_number, key_number, state)
                # change the LED value to match the latch
                _new_latch_state = get_latch(mcp_number, key_number, state)
                print(f"setting led to: {_new_latch_state}")
                led_pin.value = get_latch(mcp_number, key_number, state)

                if not _new_latch_state:
                    if state.selected_index == chip_and_index_to_index(mcp_number, key_number):
                        increment_selected(state)

            # make sure to yield during the reading of the buttons
            await asyncio.sleep(0)

        # d-pad
        up_btn.update()
        down_btn.update()
        right_btn.update()
        left_btn.update()
        middle_btn.update()
        # if down_btn.long_press:
        #     print("down longpress")
        # if not down_btn.value:
        #     print(down_btn.current_duration)

        if up_btn.fell:
            if state.mode != "selecting_file":
                state.notes[state.selected_index] += 1
            else:
                if state.selected_file is None:
                    state.selected_file = 0
                else:
                    state.selected_file += 1

                if state.selected_file >= len(state.saved_loops):
                    state.selected_file = 0
                print(f"loading: {state.selected_file}")
                state.load_state_obj(state.saved_loops[state.selected_file])

        if down_btn.fell:
            if state.mode != "selecting_file":
                state.notes[state.selected_index] -= 1
            else:
                if state.selected_file is None:
                    state.selected_file = 0
                else:
                    state.selected_file -= 1

                if state.selected_file < 0:
                    state.selected_file = len(state.saved_loops) - 1
                print(f"loading: {state.selected_file}")
                state.load_state_obj(state.saved_loops[state.selected_file])

        if right_btn.fell:
            if state.mode == "selecting_note":
                increment_selected(state)
            # state.send_off = not state.send_off
            # print(f"send off: {state.send_off}")

        if left_btn.fell:
            if state.mode == "selecting_note":
                decrement_selected(state)

        if middle_btn.long_press:
            state.selected_file = None
            state.mode = "selecting_file"
            try:
                f = open("saved_loops.json", "r")
                state.saved_loops = json.loads(f.read())["loops"]
                f.close()
            except (OSError, KeyError):
                state.saved_loops = []


        if middle_btn.fell:
            if state.mode == "selecting_file":
                if state.selected_file is None:
                    print("saving")
                    # save the current file
                    try:
                        f = open ("saved_loops.json", "r")
                        saved_loops = json.loads(f.read())
                        f.close()
                    except OSError:
                        saved_loops = {"loops":[]}

                    if "loops" not in saved_loops.keys():
                        saved_loops["loops"] = []

                    saved_loops["loops"].insert(0, {
                        "notes": state.notes,
                        "selected_index": state.selected_index
                    })

                    f = open("saved_loops.json", "w")
                    f.write(json.dumps(saved_loops))
                    f.close()
                    print("save complete")
                else:
                    # go to playback / selecting index mode
                    state.mode = "selecting_index"
            else:
                state.mode = "selecting_note" if state.mode == "selecting_index" else "selecting_index"
                print(f"new mode: {state.mode}")

        # slow down the loop a little bit, can be adjusted
        await asyncio.sleep(0.05)


async def read_encoder(state):
    while True:
        cur_position = encoder.position
        # print(cur_position)

        if state.last_position < cur_position:
            print(f"{state.last_position} -> {cur_position}")
            if state.mode == "selecting_index":
                increment_selected(state)
            elif state.mode == "selecting_note":
                state.notes[state.selected_index] += 1
        elif cur_position < state.last_position:
            print(f"{state.last_position} -> {cur_position}")
            if state.mode == "selecting_index":
                decrement_selected(state)
            elif state.mode == "selecting_note":
                state.notes[state.selected_index] -= 1
        else:
            # same
            pass

        encoder_btn.update()

        if encoder_btn.fell:
            state.mode = "selecting_note" if state.mode == "selecting_index" else "selecting_index"
            print(f"changed mode to {state.mode}")
        state.last_position = cur_position
        await asyncio.sleep(0.05)


async def update_display(state, delay=0.125):
    while True:
        b = BytesIO()
        msgpack.pack({"notes": state.notes,
                      "selected_index": state.selected_index,
                      "mode": state.mode}, b)
        b.seek(0)
        # print(b.read())
        # b.seek(0)
        display_uart.write(b.read())
        display_uart.write(b"\n")
        # display_uart.write(struct.pack("b"*len(state.notes),*state.notes))

        await asyncio.sleep(delay)

        # if state.received_ack:
        #     #display_uart.write(bytes(state.notes))
        #     b = BytesIO()
        #     msgpack.pack({"notes": state.notes, "selected_index": state.selected_index}, b)
        #     b.seek(0)
        #     print(b.read())
        #     b.seek(0)
        #     display_uart.write(b.read())
        #     display_uart.write(b"\n")
        #     state.received_ack = False
        #     #display_uart.write(struct.pack("b"*len(state.notes),*state.notes))
        #
        # else:
        #     data = display_uart.readline()
        #     if data is not None:
        #         print(f"received: {data}")
        #
        # await asyncio.sleep(delay)


async def main():
    # state = State(saved_loops.LOOP1)
    state = State()
    await asyncio.gather(
        asyncio.create_task(blink_the_leds(state, delay=0.125)),
        asyncio.create_task(read_buttons(state)),
        asyncio.create_task(blink_selected(state)),
        asyncio.create_task(update_display(state, delay=0.125)),
        asyncio.create_task(read_encoder(state))
    )


asyncio.run(main())
