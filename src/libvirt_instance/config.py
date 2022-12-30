# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

import copy
import importlib.resources
from typing import Any, Optional, TextIO

import yaml


class xml_str(str):
    pass


def yaml_xml_str_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.representer.SafeRepresenter.add_representer(xml_str, yaml_xml_str_representer)


DEFAULT_CONFIG: dict[str, dict] = {
    "defaults": {
        "cpu-model": None,  # passthrough
        "domain-type": "kvm",
    },
    "preset": {
        "domain": {
            "headless-server-x86_64": {
                "arch-name": "x86_64",
                "machine-type": "pc",
                "xml": xml_str(
                    (
                        importlib.resources.files("libvirt_instance")
                        / "domain-presets"
                        / "headless-server-x86_64.xml"
                    ).read_text()
                ),
            },
            "headless-server-aarch64": {
                "arch-name": "aarch64",
                "machine-type": "virt",
                "xml": xml_str(
                    (
                        importlib.resources.files("libvirt_instance")
                        / "domain-presets"
                        / "headless-server-aarch64.xml"
                    ).read_text()
                ),
            },
        },
        "disk": {},
        "interface": {},
    },
}


class ConfigError(Exception):
    pass


class PresetNotFoundError(ConfigError):
    pass


class UnsupportedPresetTypeError(ConfigError):
    pass


class InvalidPresetError(ConfigError):
    pass


class Config:
    def __init__(
        self,
        config_file_object: Optional[TextIO] = None,
        default_config: dict[str, dict] = DEFAULT_CONFIG,
    ) -> None:
        self._config = copy.deepcopy(default_config)

        if config_file_object is not None:
            user_config = yaml.safe_load(config_file_object)

            self._config["defaults"].update(user_config.get("defaults", {}))

            for preset_type in ("domain", "disk", "interface"):
                user_config_presets = user_config.get("preset", {}).get(preset_type, {})
                for preset_name, preset in user_config_presets.items():
                    self._config["preset"][preset_type][preset_name] = preset

        # Validation and corrections
        for preset_name, preset in self._config["preset"]["domain"].items():
            if "xml-file" in preset:
                with open(preset["xml-file"], "r") as fp:
                    preset["xml"] = xml_str(fp.read())
            # Wrap the XML into xml_str type for better formatting
            # in self.yaml().
            elif "xml" in preset:
                s = preset["xml"]
                preset["xml"] = xml_str(s)

            for key in ("machine-type", "arch-name", "xml"):
                if key not in preset:
                    raise InvalidPresetError(
                        f'Preset domain/{preset_name} is missing a value for "{key}"'
                    )

        # TODO: More preset validation.

    @property
    def config(self):
        return self._config

    @property
    def yaml(self):
        return yaml.safe_dump(self._config, indent=2, sort_keys=True)

    def get_defaults(self, key: str) -> Optional[str]:
        return self._config["defaults"].get(key, None)

    def get_preset(self, preset_type: str, preset_name: str) -> dict[str, Any]:
        if preset_type not in self._config["preset"]:
            raise UnsupportedPresetTypeError(
                f"Preset type {preset_type} is not supported"
            )

        try:
            preset = self._config["preset"][preset_type][preset_name]
        except KeyError:
            raise PresetNotFoundError(
                f"Preset {preset_type}/{preset_name} not found in the config"
            )

        return preset
