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
