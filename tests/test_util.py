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
