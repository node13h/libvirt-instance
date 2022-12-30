# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

import tempfile
from io import StringIO
from pathlib import Path

import pytest

from libvirt_instance import config


def test_default_config():
    c = config.Config()

    assert len(c.get_preset("domain", "headless-server-x86_64")["xml"]) > 0


def test_yaml_config():
    f = StringIO(
        """---
defaults:
  domain-type: qemu
preset:
  domain:
    empty:
      arch-name: x86_64
      machine-type: pc
      xml: "<domain></domain>"
"""
    )
    c = config.Config(f)

    domain_preset = c.get_defaults("domain-type")
    assert domain_preset == "qemu"

    assert c.get_preset("domain", "empty")["xml"] == "<domain></domain>"


def test_builtin_setting_override():
    f = StringIO(
        """---
preset:
  domain:
    headless-server-x86_64:
      arch-name: x86_64
      machine-type: pc
      xml: "<domain></domain>"
"""
    )
    c = config.Config(f)

    assert (
        c.get_preset("domain", "headless-server-x86_64")["xml"] == "<domain></domain>"
    )


def test_non_existing_default():
    c = config.Config()

    assert c.get_defaults("DOES-NOT-EXIST") is None


def test_get_preset():
    f = StringIO(
        """---
preset:
  disk:
    test:
      pool: default
      bus: virtio
      cache: none
"""
    )
    c = config.Config(f)

    assert c.get_preset("disk", "test") == {
        "pool": "default",
        "bus": "virtio",
        "cache": "none",
    }


def test_unsupported_preset_type():
    c = config.Config()

    with pytest.raises(config.UnsupportedPresetTypeError):
        c.get_preset("FOO", "test")


def test_missing_preset():
    c = config.Config()

    with pytest.raises(config.PresetNotFoundError):
        c.get_preset("disk", "test")


def test_invalid_preset():
    f = StringIO(
        """---
preset:
  domain:
    test: {}
"""
    )
    with pytest.raises(config.InvalidPresetError):
        config.Config(f)


def test_config_yaml():
    f = StringIO(
        """---
preset:
  domain:
    test1:
      arch-name: x86_64
      machine-type: pc
      xml: |
        <domain>
        </domain>
"""
    )

    default_config = {
        "defaults": {
            "cpu-model": None,
            "domain-type": "kvm",
        },
        "preset": {
            "domain": {
                "test2": {
                    "arch-name": "x86_64",
                    "machine-type": "pc",
                    "xml": "<domain>\n</domain>\n",
                }
            },
        },
    }

    c = config.Config(f, default_config=default_config)

    assert (
        c.yaml
        == """defaults:
  cpu-model: null
  domain-type: kvm
preset:
  domain:
    test1:
      arch-name: x86_64
      machine-type: pc
      xml: |
        <domain>
        </domain>
    test2:
      arch-name: x86_64
      machine-type: pc
      xml: |
        <domain>
        </domain>
"""
    )


def test_xml_file():

    with tempfile.TemporaryDirectory() as temp_dir:
        xml_file = Path(temp_dir) / "base.xml"

        with open(xml_file, "w") as fp:
            fp.write("<domain>\n</domain>")

        f = StringIO(
            f"""---
defaults:
  cpu-model: null
  domain-type: kvm
preset:
  domain:
    test:
      arch-name: x86_64
      machine-type: pc
      xml-file: "{xml_file}"
"""
        )

        default_config = {
            "defaults": {},
            "preset": {
                "domain": {},
                "disk": {},
                "interface": {},
            },
        }

        c = config.Config(f, default_config=default_config)

    assert c.get_preset("domain", "test")["xml"] == "<domain>\n</domain>"
