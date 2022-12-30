# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

from libvirt_instance import util


def test_index_to_drive_name_zero():
    assert util.index_to_drive_name(0) == "a"


def test_index_to_drive_name_1():
    assert util.index_to_drive_name(1) == "b"


def test_index_to_drive_name_26():
    assert util.index_to_drive_name(26) == "aa"


def test_index_to_drive_name_702():
    assert util.index_to_drive_name(702) == "aaa"


def test_index_to_drive_name_18277():
    assert util.index_to_drive_name(18277) == "zzz"


def test_index_to_drive_name_1403():
    assert util.index_to_drive_name(1403) == "baz"


def test_human_size_units_to_bytes_no_units():
    assert util.human_size_units_to_bytes("12345") == 12345


def test_human_size_units_to_bytes_space():
    assert util.human_size_units_to_bytes("12345  B") == 12345


def test_human_size_units_to_bytes_bytes():
    assert util.human_size_units_to_bytes("12345B") == 12345


def test_human_size_units_to_bytes_kilobytes():
    assert util.human_size_units_to_bytes("12345KB") == 12345000


def test_human_size_units_to_bytes_kibibytes():
    assert util.human_size_units_to_bytes("12345KiB") == 12641280
