import time
import datetime
import logging
import usb
import usb.core
import usb.util
from usb.backend import libusb1

import pystray
from PIL import Image

import threading
import darkdetect
import numpy as np


VENDOR_ID_WIRELESS = 0x1532
VIPER_V2_WIRELESS = 0x00A5

VENDOR_ID_WIRED = 0x1532
VIPER_V2_WIRED = 0x00A6

TRANSACTION_ID = b"\x1f"


def get_mouse():
    device = usb.core.find(idVendor=VENDOR_ID_WIRELESS,
                           idProduct=VIPER_V2_WIRELESS)
    if not device:
        device = usb.core.find(idVendor=VENDOR_ID_WIRED,
                               idProduct=VIPER_V2_WIRED)
        if not device:
            return [None, None]
        return [device, True]
    return [device, False]


def generate_report_binary(TRANS_ID=b"\x1f"):
    # report_status = 0x00
    # report_transaction_id = TRANS_ID
    # report_remaining_packets = 0x0000
    # report_protocol_type = 0x00
    # report_data_size = 0x02
    # report_command_class = 0x07
    # report_command_id = 0x80
    # report_arguments = bytes(80)
    # report_crc = 0x00
    report = b"\x00" + TRANS_ID + b"\x00\x00\x00\x02\x07\x80"
    crc = 0
    for i in report[2:]:
        crc ^= i
    report += bytes(80)
    report += bytes([crc, 0])
    return report


def get_battery():
    mouse, wireless = get_mouse()
    if not mouse:
        return 0.0
    msg = generate_report_binary(TRANSACTION_ID)

    logging.debug(f"Sending message to mouse: {msg}")

    mouse.set_configuration()
    usb.util.claim_interface(mouse, 0)
    # send request (battery), see razer_send_control_msg in razercommon.c in OpenRazer driver for detail
    _ = mouse.ctrl_transfer(bmRequestType=0x21, bRequest=0x09, wValue=0x300, data_or_wLength=msg,
                              wIndex=0x00)

    # needed by PyUSB
    usb.util.dispose_resources(mouse)
    # if the mouse is wireless, need to wait before getting response
    if wireless:
        time.sleep(0.5305)
    # receive response
    result = mouse.ctrl_transfer(
        bmRequestType=0xa1, bRequest=0x01, wValue=0x300, data_or_wLength=90, wIndex=0x00)
    usb.util.dispose_resources(mouse)
    usb.util.release_interface(mouse, 0)
    logging.debug(f"Message received from the mouse: {list(result)}")
    # the raw battery level is in 0 - 255, scale it to 100 for human, correct to 2 decimal places

    return result[9] / 255 * 100


def create_image(fill, empty='img/mouse.png', full='img/mousefull.png'):
    empty = Image.open(empty).convert('RGBA')
    full = Image.open(full).convert('RGBA')

    width, height = full.size
    bottom_height = int((fill / 100) * height)

    # Crop the bottom X% of the overlay
    bottom_overlay = full.crop((0, height - bottom_height, width, height))

    # Calculate the position to paste the bottom overlay onto the background
    bg_width, bg_height = empty.size
    paste_position = (0, bg_height - bottom_height)  # Align bottom

    # Paste the cropped overlay onto the background
    empty.paste(bottom_overlay, paste_position, bottom_overlay)

    empty.alpha_composite(bottom_overlay, dest=(
        paste_position[0], paste_position[1]))

    square_size = max(width, height)
    square_img = Image.new("RGBA", (square_size, square_size), (0, 0, 0, 0))

    # Calculate the position to center the original image
    x_offset = (square_size - width) // 2
    y_offset = (square_size - height) // 2

    # Paste the original image onto the square canvas
    square_img.paste(empty, (x_offset, y_offset), empty)
    if darkdetect.isDark():
        data = np.array(square_img)
        red, green, blue, alpha = data.T
        black = (red < 10) & (blue < 10) & (green < 10)
        data[..., :-1][black.T] = (200, 200, 200)
        square_img = Image.fromarray(data, mode='RGBA')
    return square_img


def update(icon):
    while True:
        res = get_battery()
        icon.icon = create_image(res)
        # icon.menu_items.pop()
        # icon.menu_items.append(pystray.MenuItem(f'Mouse Battery: {round(res, 0)}%',
        #     lambda: f'Battery Level: {round(res, 0)}%'))
        icon.update_menu()
        logging.info(f"Updating {datetime.datetime.now().strftime("%I:%M%p on %B %d, %Y")}")
        time.sleep(60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    res = get_battery()
    menu = pystray.Menu(
        pystray.MenuItem(lambda _ : f'Mouse Battery: {int(res)}%', lambda: f'Battery Level: {int(res)}%'),
        pystray.MenuItem('Exit', lambda _: icon.stop())
        )
    icon = pystray.Icon(
        'Icon',
        icon=create_image(get_battery()),
        menu=menu)
    thread = threading.Thread(daemon=True, target=update, args=(icon,))
    thread.start()
    icon.run()
