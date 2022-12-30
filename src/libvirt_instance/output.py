# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

import json
from typing import Mapping, Union


def formatted(data: Mapping[str, Union[str, list]], format: str):
    if format == "json":
        return json.dumps(data, indent=2, sort_keys=True)
