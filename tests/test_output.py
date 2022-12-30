# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

from libvirt_instance import output


def test_json_format():
    s = output.formatted({"foo": "test", "bar": "baz"}, "json")

    assert (
        s
        == """{
  "bar": "baz",
  "foo": "test"
}"""
    )
