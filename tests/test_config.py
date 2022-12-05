from io import StringIO

import pytest

from libvirt_instance import config


def test_default_config():
    c = config.Config()

    domain_preset = c.get_defaults("domain-preset")
    assert len(domain_preset) > 0
    assert len(c.get_preset("domain", domain_preset)["xml"]) > 0


def test_yaml_config():
    f = StringIO(
        """---
defaults:
  domain-preset: empty
preset:
  domain:
    empty:
      xml: "<domain></domain>"
"""
    )
    c = config.Config(f)

    domain_preset = c.get_defaults("domain-preset")
    assert domain_preset == "empty"

    assert c.get_preset("domain", "empty")["xml"] == "<domain></domain>"


def test_builtin_setting_override():
    f = StringIO(
        """---
preset:
  domain:
    linux-server:
      xml: "<domain></domain>"
"""
    )
    c = config.Config(f)

    assert c.get_preset("domain", "linux-server")["xml"] == "<domain></domain>"


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
    c = config.Config(f)

    with pytest.raises(config.InvalidPresetError):
        c.get_preset("domain", "test")
