# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

import argparse
import importlib.metadata
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

import libvirt  # type: ignore
import yaml

from libvirt_instance import output, seed_image, util
from libvirt_instance.config import Config
from libvirt_instance.domain import DomainDefinition, Volume

logger = logging.getLogger(__name__)


class CliError(Exception):
    pass


def parse_spec(spec: str) -> tuple:
    args = []
    kwargs: dict = {}

    if spec:
        for item in spec.split(","):
            parts = item.split("=", 1)
            if len(parts) == 1:
                args.append(parts[0])
            else:
                kwargs[parts[0]] = parts[1]

    return args, kwargs


def parse_disk_spec(spec: str) -> tuple:
    args, kwargs = parse_spec(spec)

    if len(args) != 2:
        raise ValueError(
            "Disk spec must specify a preset name and a size. "
            "Got {}".format(",".join(args))
        )

    return args[0], util.human_size_units_to_bytes(args[1]), kwargs


def parse_generic_spec(spec: str) -> tuple:
    args, kwargs = parse_spec(spec)

    if len(args) != 1:
        raise ValueError(
            "Spec must specify a preset name. Got {}".format(",".join(args))
        )

    return args[0], kwargs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="libvirt-instance",
        description=importlib.metadata.metadata("libvirt-instance")["Summary"],
    )

    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"),
        help="log level",
    )

    parser.add_argument(
        "--output-format", default="json", choices=("json",), help="output format"
    )

    parser.add_argument(
        "--config-file",
        type=Path,
        default=Path("/etc/libvirt-instance-config.yaml"),
        help="location of the configuration file",
    )

    parser.add_argument(
        "--connect", "-c", default="qemu:///system", help="libvirt connection string"
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="sub-command help"
    )

    subparsers.add_parser("version", help="show version")

    subparsers.add_parser("get-domain-presets", help="list all domain presets")

    subparsers.add_parser("get-config", help="show current config")

    parser_create = subparsers.add_parser("create", help="create a VM")

    parser_create.add_argument("name", help="VM name")

    parser_create.add_argument(
        "--cpu-model",
        help="virtual CPU model; defaults to host passthrough when not set",
    )

    parser_create.add_argument("--arch-name", help="architecture name")

    parser_create.add_argument("--machine-type", help="virtual hardware model")

    parser_create.add_argument(
        "--domain-type", help="Libvirt domain type, e.g. kvm, or qemu"
    )

    parser_create.add_argument(
        "--domain-preset",
        help="domain preset name in the config file to use",
    )

    parser_create.add_argument(
        "--memory",
        type=util.human_size_units_to_bytes,
        required=True,
        help=(
            "amount of RAM memory in to allocate. "
            "supported units are: {}".format(", ".join(filter(None, util.SIZE_UNITS)))
        ),
    )

    parser_create.add_argument(
        "--vcpu", type=int, required=True, help="number of vCPUs to configure"
    )

    parser_create.add_argument(
        "--disk",
        type=parse_disk_spec,
        action="append",
        help='comma-separated disk spec; format is: "preset-name,size,key=value,..."',
    )

    parser_create.add_argument(
        "--nic",
        type=parse_generic_spec,
        action="append",
        help='comma-separated network interface spec; format is: "preset-name,key=value,..."',
    )

    parser_create.add_argument(
        "--cloud-seed-disk",
        type=parse_generic_spec,
        help='comma-separated cloud seed disk spec; format is: "preset-name,key=value,..."',
    )

    parser_create.add_argument(
        "--cloud-user-data-file",
        type=Path,
        help="location of the cloud-init user-data file; needs --cloud-seed-disk",
    )

    parser_create.add_argument(
        "--cloud-network-config-file",
        type=Path,
        help="location of the cloud-init network-config file; needs --cloud-seed-disk",
    )

    return parser.parse_args()


def cmd_get_domain_presets(args: argparse.Namespace, config: Config):
    result: dict[str, list] = {}

    for preset_name, preset in config.config["preset"]["domain"].items():
        arch_name = preset["arch-name"]
        if arch_name not in result:
            result[arch_name] = []

        result[arch_name].append(
            {
                "preset-name": preset_name,
                "machine-type": preset["machine-type"],
            }
        )

    print(output.formatted(result, args.output_format))


def cmd_get_config(args: argparse.Namespace, config: Config):
    print(config.yaml)


def cmd_create(args: argparse.Namespace, config: Config):
    instance_id = str(uuid.uuid4())

    cpu_model = args.cpu_model or config.get_defaults("cpu-model")

    domain_type = args.domain_type or config.get_defaults("domain-type")
    if not domain_type:
        raise CliError("Please provide domain type")

    domain_preset_name = args.domain_preset or config.get_defaults("domain-preset")
    if not domain_preset_name:
        raise CliError(
            "Please use --domain-preset to select a domain preset to base the VM on"
        )

    domain_preset = config.get_preset("domain", domain_preset_name)

    machine_type = args.machine_type or domain_preset["machine-type"]
    arch_name = args.arch_name or domain_preset["arch-name"]

    # Resolve preset names and arguments in advance for implied validation.
    disks = []
    for i, (preset_name, disk_size, kwargs) in enumerate(args.disk):
        preset = config.get_preset("disk", preset_name)

        disk = preset.copy()

        disk["name"] = f"{args.name}-disk{i}"
        disk["size"] = disk_size

        for key in ("pool", "bus", "cache", "source", "source-pool"):
            if key in kwargs:
                disk[key] = kwargs[key]

        for key in ("boot-order",):
            if key in kwargs:
                disk[key] = int(kwargs[key])

        disks.append(disk)

    nics = []
    for preset_name, kwargs in args.nic:
        preset = config.get_preset("interface", preset_name)

        nic = preset.copy()

        for key in ("model-type", "network", "bridge", "mac-address"):
            if key in kwargs:
                nic[key] = kwargs[key]

        for key in ("boot-order", "mtu"):
            if key in kwargs:
                nic[key] = int(kwargs[key])

        nics.append((nic, kwargs))

    seed_disk: Optional[dict[str, Any]]

    if args.cloud_seed_disk is not None:
        preset_name, kwargs = args.cloud_seed_disk
        preset = config.get_preset("disk", preset_name)
        preset_type = preset["type"]

        if preset_type != "volume":
            raise CliError(
                f"Preset {preset_name} specified for the seed disk is of type {preset_type}. "
                f"Only presets of type volume can be used for cloud seed disks."
            )

        seed_disk = {}

        for key in ("pool", "bus", "cache"):
            seed_disk[key] = kwargs.get(key, preset[key])

        meta_data = {
            "instance-id": instance_id,
            "local-hostname": args.name,
        }
        meta_data_body = yaml.dump(meta_data)

        if args.cloud_user_data_file is not None:
            with open(args.cloud_user_data_file, "r") as fp:
                user_data_body = fp.read()
        else:
            # user-data is not optional, simulate empty file if missing.
            user_data_body = ""

        if args.cloud_network_config_file is not None:
            with open(args.cloud_network_config_file, "r") as fp:
                network_config_body = fp.read()
        else:
            network_config_body = None  # network-config is optional.

        seed_disk["fp"], seed_disk["size"] = seed_image.build(
            meta_data_body, user_data_body, network_config_body
        )

    else:
        seed_disk = None

    conn = libvirt.open(args.connect)

    d = DomainDefinition(
        args.name,
        ram_bytes=args.memory,
        vcpus=args.vcpu,
        basexml=domain_preset["xml"],
        libvirt_conn=conn,
        domain_type=domain_type,
        machine=machine_type,
        uuid=instance_id,
        arch_name=arch_name,
        cpu_model=cpu_model,
    )

    for disk in disks:
        disk_type = disk["type"]

        if disk_type == "volume":
            v = Volume(
                disk["name"],
                create_size_bytes=disk_size,
                libvirt_conn=conn,
                pool_name=disk["pool"],
                source_name=disk.get("source", None),
                source_pool_name=disk.get("source-pool", None),
            )

            d.add_disk(
                v,
                bus=disk["bus"],
                cache=disk["cache"],
                boot_order=disk.get("boot-order", None),
            )
        else:
            raise CliError(f"Disk type {disk_type} is unsupported")

    if seed_disk is not None:

        v = Volume(
            f"{args.name}-seed",
            create_size_bytes=seed_disk["size"],
            libvirt_conn=conn,
            pool_name=seed_disk["pool"],
        )

        v.upload(seed_disk["fp"], seed_disk["size"])

        d.add_disk(
            v,
            bus=seed_disk["bus"],
            cache=seed_disk["cache"],
        )

    for nic, kwargs in nics:
        nic_type = nic["type"]
        if nic_type == "network":
            d.add_network_interface(
                nic["network"],
                model_type=nic["model-type"],
                mac_address=nic.get("mac-address", None),
                boot_order=nic.get("boot-order", None),
                mtu=nic.get("mtu", None),
            )
        elif nic_type == "bridge":
            d.add_bridge_interface(
                nic["bridge"],
                model_type=nic["model-type"],
                mac_address=nic.get("mac-address", None),
                boot_order=nic.get("boot-order", None),
                mtu=nic.get("mtu", None),
            )
        else:
            raise CliError(f"Network interface type {nic_type} is unsupported")

    d.define()

    print(output.formatted({"instance-id": instance_id}, args.output_format))


def main() -> None:

    args = parse_args()

    logging.basicConfig(level=args.log_level)

    if args.config_file.exists():
        with open(args.config_file, "r") as f:
            config = Config(f)
    else:
        config = Config()

    try:
        if args.command == "version":
            print(importlib.metadata.version("libvirt-instance"))
        elif args.command == "get-domain-presets":
            cmd_get_domain_presets(args, config)
        elif args.command == "get-config":
            cmd_get_config(args, config)
        elif args.command == "create":
            cmd_create(args, config)
    except CliError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
