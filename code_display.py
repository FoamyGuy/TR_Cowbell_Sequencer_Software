import gc
import json
import time
from io import BytesIO
import displayio
import board
import busio
import msgpack
import terminalio
from adafruit_display_text.bitmap_label import Label
from vectorio import Circle, Rectangle
from cedargrove_midi_tools import note_to_name


def validate_data_obj(data_obj):
    if not isinstance(data_obj, dict):
        return False
    if "notes" not in data_obj.keys() or "selected_index" not in data_obj.keys():
        return False
    if not isinstance(data_obj['notes'], list):
        return False

    return True

STATUS_BAR_HEIGHT = 20
MARGIN = 2

NOTE_CIRCLE_R = 12
NOTE_CIRCLE_MARGIN = 10

uart = busio.UART(board.SDA, board.SCL, baudrate=19200, receiver_buffer_size=2048 * 2)

main_group = displayio.Group()
steps_group = displayio.Group()

display = board.DISPLAY
display.auto_refresh = False

print(f"display width: {display.width}")
display.root_group = main_group

palette = displayio.Palette(3)

palette[0] = 0x222222
palette[1] = 0xbbbbbb
palette[2] = 0xbbaa00


status_bar_group = displayio.Group()

steps_icon = displayio.OnDiskBitmap("icon_step_select.bmp")
notes_icon = displayio.OnDiskBitmap("icon_note_select.bmp")
file_icon = displayio.OnDiskBitmap("icon_file_mode.bmp")

mode_icon_tilegrid = displayio.TileGrid(steps_icon, pixel_shader=steps_icon.pixel_shader)

# mode_icon_tilegrid.bitmap = file_icon
# mode_icon_tilegrid.pixel_shader = file_icon.pixel_shader

status_bar_group.append(mode_icon_tilegrid)

main_group.append(status_bar_group)

sequence_circles = []
sequence_rects = []
sequence_lbls = []

step_rects = []

for row in range(2):
    for col in range(8):
        _width = display.width//8 - MARGIN
        _height = (display.height-STATUS_BAR_HEIGHT)//2 - MARGIN
        #print(f"{_width} x {_height}")
        _step_rect = Rectangle(pixel_shader=palette,
                               width=_width,
                               height=_height,
                               x=(col * (_width + MARGIN)),
                               y=(row * (_height + MARGIN))
                               )
        #print(f"({_step_rect.x}, {_step_rect.y})")
        step_rects.append(_step_rect)


        _lbl = Label(terminalio.FONT, text="", color=0x000000, scale=2)
        _lbl.anchor_point = (0.5, 0.5)
        _lbl.anchored_position = ((_step_rect.x + _step_rect.width//2),
                                  (_step_rect.y + _step_rect.height//2))


        sequence_lbls.append(_lbl)

        steps_group.append(_step_rect)
        steps_group.append(_lbl)


steps_group.y = STATUS_BAR_HEIGHT
print(f"notes group x: {steps_group.x}")
main_group.append(steps_group)

def insert (source_str, insert_str, pos):
    return source_str[:pos] + insert_str + source_str[pos:]

prev_obj = None

display.refresh()
while True:

    start_time = time.monotonic()
    #print(f"beginning of loop: {time.monotonic() - start_time}")
    # data = uart.read(64)  # read up to 32 bytes
    # uart.reset_input_buffer()
    data = uart.readline()
    # print(f"after readline: {time.monotonic() - start_time}")
    # print(data)  # this is a bytearray type
    if data is not None:
        # print(len(data))
        # print(data)

        # gc.collect()

        # uart.write(b"ACK\n")
        # print(gc.mem_free())
        b = BytesIO()
        b.write(data)
        b.seek(0)
        # print(f"after bytesio write and seek: {time.monotonic() - start_time}")
        try:
            data_obj = msgpack.unpack(b)
            print(json.dumps(data_obj))
            # print(f"after unpack: {time.monotonic() - start_time}")
            if validate_data_obj(data_obj):

                if data_obj["mode"] == "selecting_index":
                    if mode_icon_tilegrid.bitmap != steps_icon:
                        mode_icon_tilegrid.bitmap = steps_icon
                        mode_icon_tilegrid.pixel_shader = steps_icon.pixel_shader

                elif data_obj["mode"] == "selecting_note":
                    if mode_icon_tilegrid.bitmap != notes_icon:
                        mode_icon_tilegrid.bitmap = notes_icon
                        mode_icon_tilegrid.pixel_shader = notes_icon.pixel_shader
                elif data_obj["mode"] == "selecting_file":
                    if mode_icon_tilegrid.bitmap != file_icon:
                        mode_icon_tilegrid.bitmap = file_icon
                        mode_icon_tilegrid.pixel_shader = file_icon.pixel_shader

                # print(f"after validate: {time.monotonic() - start_time}")
                #print(data_obj)
                for i, note in enumerate(data_obj["notes"]):
                    if note != 0:
                        if i != data_obj["selected_index"]:
                            step_rects[i].color_index = 1
                        else:
                            step_rects[i].color_index = 2

                        #sequence_lbls[i].text = str(note)
                        sequence_lbls[i].text = insert(note_to_name(note), "\n", -1) if len(note_to_name(note)) == 3 else note_to_name(note)


                        #sequence_circles[i].color_index = 1
                    else:
                        step_rects[i].color_index = 0
                        if sequence_lbls[i].text != "":
                            sequence_lbls[i].text = ""

                        #sequence_circles[i].color_index = 0
                # print(f"after first loop: {time.monotonic() - start_time}")

                # for i, rect in enumerate(sequence_rects):
                #
                #     if i != data_obj["selected_index"]:
                #         step_rects[i].color_index = 1
                    #    rect.hidden = True


                # print(f"after 2nd loop: {time.monotonic() - start_time}")

                #if data_obj['selected_index'] >= 0:
                #    sequence_rects[data_obj['selected_index']].hidden = False

                if data_obj != prev_obj:
                    #print(f"before refresh: {time.monotonic() - start_time}")
                    display.refresh()
                else:
                    pass
                    #print(f"no refresh: {time.monotonic() - start_time}")
                # print(f"before refresh: {time.monotonic() - start_time}")
                # display.refresh()

            prev_obj = data_obj
            #print(f"end of loop: {time.monotonic() - start_time}")
        except EOFError:
            print("EOF")
        except ValueError as e:
            print("Short Read error")
            print(e)
    time.sleep(0.001)
    #print(f"iteration took: {time.monotonic() - start_time}")
