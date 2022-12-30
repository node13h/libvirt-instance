# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

from io import BytesIO

import pycdlib

from libvirt_instance import seed_image


def test_build():
    iso_fp, size = seed_image.build("instance-id: foo", "#cloud-config")

    iso = pycdlib.PyCdlib()

    iso.open_fp(iso_fp)

    files = {
        r.file_identifier().decode("utf-16be")
        for r in iso.list_children(joliet_path="/")
    }

    assert "meta-data" in files
    assert "user-data" in files
    assert "network-config" not in files

    file_data = BytesIO()
    iso.get_file_from_iso_fp(file_data, joliet_path="/meta-data")

    assert file_data.getvalue().decode("utf-8") == "instance-id: foo"

    file_data = BytesIO()
    iso.get_file_from_iso_fp(file_data, joliet_path="/user-data")

    assert file_data.getvalue().decode("utf-8") == "#cloud-config"


def test_build_with_network_config():
    iso_fp, size = seed_image.build("instance-id: foo", "#cloud-config", "---")

    iso = pycdlib.PyCdlib()

    iso.open_fp(iso_fp)

    files = {
        r.file_identifier().decode("utf-16be")
        for r in iso.list_children(joliet_path="/")
    }

    assert "network-config" in files

    file_data = BytesIO()
    iso.get_file_from_iso_fp(file_data, joliet_path="/network-config")

    assert file_data.getvalue().decode("utf-8") == "---"
