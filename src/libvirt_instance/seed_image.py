# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

# See https://cloudinit.readthedocs.io/en/latest/topics/datasources/nocloud.html

from io import BytesIO
from typing import BinaryIO, Optional

import pycdlib


def build(
    meta_data_body: str, user_data_body: str, network_config_body: Optional[str] = None
) -> tuple[BinaryIO, int]:
    iso_fp = BytesIO()

    iso = pycdlib.PyCdlib()
    iso.new(vol_ident="cidata", joliet=3, rock_ridge="1.09")

    iso.add_fp(
        BytesIO(meta_data_body.encode("utf-8")),
        len(meta_data_body),
        "/METADATA.;1",
        joliet_path="/meta-data",
        rr_name="meta-data",
    )

    iso.add_fp(
        BytesIO(user_data_body.encode("utf-8")),
        len(user_data_body),
        "/USERDATA.;1",
        joliet_path="/user-data",
        rr_name="user-data",
    )

    if network_config_body is not None:
        iso.add_fp(
            BytesIO(network_config_body.encode("utf-8")),
            len(network_config_body),
            "/NETWORK.;1",
            joliet_path="/network-config",
            rr_name="network-config",
        )

    iso.write_fp(iso_fp)

    iso.close()

    size = len(iso_fp.getvalue())

    iso_fp.seek(0)

    return iso_fp, size
