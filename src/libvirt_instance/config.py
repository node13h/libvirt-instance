import importlib.resources
from typing import Any, Optional, TextIO

import yaml


class ConfigError(Exception):
    pass


class PresetNotFoundError(ConfigError):
    pass


class UnsupportedPresetTypeError(ConfigError):
    pass


class InvalidPresetError(ConfigError):
    pass


class Config:
    def __init__(self, config_file_object: Optional[TextIO] = None) -> None:
        self._config: dict[str, dict] = {
            "defaults": {
                "cpu-model": None,  # passthrough
                "domain-type": "kvm",
            },
            "preset": {
                "domain": {
                    "headless-server-x86_64": {
                        "arch-name": "x86_64",
                        "machine-type": "pc",
                    },
                },
                "disk": {
                    "local": {
                        "type": "volume",
                        "pool": "default",
                        "bus": "virtio",
                        "cache": "none",
                    }
                },
                "interface": {
                    "nat": {
                        "type": "network",
                        "model-type": "virtio",
                        "network": "default",
                    }
                },
            },
        }

        for domain_preset in ("headless-server-x86_64",):
            resource = (
                importlib.resources.files("libvirt_instance")
                / "domain-presets"
                / f"{domain_preset}.xml"
            )
            self._config["preset"]["domain"][domain_preset][
                "xml"
            ] = resource.read_text()

        if config_file_object is not None:
            user_config = yaml.safe_load(config_file_object)

            self._config["defaults"].update(user_config.get("defaults", {}))

            for preset_type in ("domain", "disk", "interface"):
                user_config_presets = user_config.get("preset", {}).get(preset_type, {})
                for preset_name, preset in user_config_presets.items():
                    self._config["preset"][preset_type][preset_name] = preset

        for preset_type in ("domain",):
            for preset_name, preset in self._config["preset"][preset_type].items():
                for key in ("machine-type", "arch-name", "xml"):
                    if key not in preset:
                        raise InvalidPresetError(
                            f'Preset {preset_type}/{preset_name} is missing a value for "{key}"'
                        )

        # TODO: More preset validation.

    @property
    def config(self):
        return self._config

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
