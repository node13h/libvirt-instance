# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

import re
from string import ascii_lowercase

SIZE_UNITS = {
    None: 1,
    "B": 1,
    "KB": 10**3,
    "MB": 10**6,
    "GB": 10**9,
    "TB": 10**12,
    "PB": 10**15,
    "KiB": 2**10,
    "MiB": 2**20,
    "GiB": 2**30,
    "TiB": 2**40,
    "PiB": 2**50,
}


# https://rwmj.wordpress.com/2011/01/09/how-are-linux-drives-named-beyond-drive-26-devsdz/
def index_to_drive_name(idx: int) -> str:
    """
    Convert decimal to bijective base-26
    """

    coll = []
    d = idx + 1

    while d:
        d -= 1
        r = d % 26
        coll.append(ascii_lowercase[r])
        d //= 26

    return "".join(reversed(coll))


def human_size_units_to_bytes(size: str):
    """
    Convert human-readable data size units into bytes.
    """

    regex = r"^(?P<number>\d+)\s*(?P<unit>[iA-Z]{1,3})?$"

    m = re.match(regex, size)
    if m:
        number = int(m.group("number"))
        unit = m.group("unit")
    else:
        raise ValueError(f"Invalid value {size}")

    try:
        return number * SIZE_UNITS[unit]
    except KeyError:
        raise ValueError(f"Unit {unit} is not supported")
