# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

import pytest

from libvirt_instance import cli


def test_parse_spec_empty():
    assert cli.parse_spec("") == ([], {})


def test_parse_spec_one_arg():
    assert cli.parse_spec("arg1") == (["arg1"], {})


def test_parse_spec_multiple_args():
    assert cli.parse_spec("arg1,arg2") == (["arg1", "arg2"], {})


def test_parse_spec_kwargs_only():
    assert cli.parse_spec("key=value") == ([], {"key": "value"})


def test_parse_spec_args_and_kwargs():
    assert cli.parse_spec("arg1,arg2,key=value") == (["arg1", "arg2"], {"key": "value"})


def test_parse_disk_spec():
    assert cli.parse_disk_spec("test,1MiB,key=value") == (
        "test",
        1048576,
        {"key": "value"},
    )


def test_parse_disk_spec_invalid():
    with pytest.raises(ValueError):
        cli.parse_disk_spec("test,key=value")


def test_parse_generic_spec():
    assert cli.parse_generic_spec("test,key=value") == ("test", {"key": "value"})


def test_parse_generic_spec_invalid():
    with pytest.raises(ValueError):
        cli.parse_generic_spec("")


def test_parse_cipher():
    assert cli.parse_cipher("aes-128-cbc-sha256") == {
        "name": "aes",
        "size": 128,
        "mode": "cbc",
        "hash": "sha256",
    }


def test_parse_ivgen():
    assert cli.parse_ivgen("essiv-sha256") == {"name": "essiv", "hash": "sha256"}
