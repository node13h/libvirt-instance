import argparse
import importlib.metadata
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

import libvirt  # type: ignore
import yaml

from libvirt_instance import seed_image, util
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
            "Disk spec must specify preset name and size. "
            "Got {}".format(",".join(args))
        )

    return args[0], util.human_size_units_to_bytes(args[1]), kwargs


def parse_nic_spec(spec: str) -> tuple:
    args, kwargs = parse_spec(spec)

    if len(args) != 1:
        raise ValueError(
            "Network interface spec must specify preset name. "
            "Got {}".format(",".join(args))
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
        "--config-file",
        type=Path,
        default=Path("/etc/libvirt-instance.conf"),
        help="location of the configuration file",
    )

    parser.add_argument(
        "--connect", "-c", default="qemu:///system", help="libvirt connection string"
    )

    subparsers = parser.add_subparsers(dest="command", help="sub-command help")

    subparsers.add_parser("version", help="show version")

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
        type=parse_nic_spec,
        action="append",
        help='comma-separated network interface spec; format is: "preset-name,key=value,..."',
    )

    parser_create.add_argument(
        "--cloud-seed-disk",
        help=(
            "preset name to use when creating the cloud seed disk; "
            "see https://cloudinit.readthedocs.io/en/latest/topics/datasources/nocloud.html for more info"
        ),
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


def cmd_create(args: argparse.Namespace, config: Config):
    instance_id = str(uuid.uuid4())

    cpu_model = args.cpu_model or config.get_defaults("cpu-model")
    arch_name = args.arch_name or config.get_defaults("arch-name")
    if not arch_name:
        raise CliError("Please provide architecture name")
    machine_type = args.machine_type or config.get_defaults("machine-type")
    if not machine_type:
        raise CliError("Please provide machine type")
    domain_type = args.domain_type or config.get_defaults("domain-type")
    if not domain_type:
        raise CliError("Please provide domain type")
    domain_preset = args.domain_preset or config.get_defaults("domain-preset")
    if not domain_preset:
        raise CliError("Please select a domain preset to base the VM on")

    # Resolve preset names in advance for implied validation.
    disks = []
    for i, (preset_name, disk_size, kwargs) in enumerate(args.disk):
        preset = config.get_preset("disk", preset_name)
        disks.append((i, preset, disk_size, kwargs))

    nics = []
    for preset_name, kwargs in args.nic:
        preset = config.get_preset("interface", preset_name)
        nics.append((preset, kwargs))

    seed_disk: Optional[dict[str, Any]]

    if args.cloud_seed_disk is not None:
        seed_disk_preset = config.get_preset("disk", args.cloud_seed_disk)

        meta_data = {
            "instance-id": instance_id,
            "local-hostname": args.name,
        }
        meta_data_body = yaml.dump(meta_data)

        if args.cloud_user_data_file is not None:
            with open(args.cloud_user_data_file, "r") as fp:
                user_data_body = fp.read()
        else:
            user_data_body = (
                ""  # user-data is not optional, simulate empty file if missing.
            )

        if args.cloud_network_config_file is not None:
            with open(args.cloud_network_config_file, "r") as fp:
                network_config_body = fp.read()
        else:
            network_config_body = None  # network-config is optional.

        seed_iso_fp, seed_iso_size = seed_image.build(
            meta_data_body, user_data_body, network_config_body
        )

        seed_disk = {
            "size": seed_iso_size,
            "fp": seed_iso_fp,
            "preset": seed_disk_preset,
        }
    else:
        seed_disk = None

    conn = libvirt.open(args.connect)

    d = DomainDefinition(
        args.name,
        ram_bytes=args.memory,
        vcpus=args.vcpu,
        basexml=config.get_preset("domain", args.domain_preset)["xml"],
        libvirt_conn=conn,
        domain_type=domain_type,
        machine=machine_type,
        uuid=instance_id,
        arch_name=arch_name,
        cpu_model=cpu_model,
    )

    for i, preset, disk_size, kwargs in disks:
        v = Volume(
            f"{args.name}-disk{i}",
            create_size_bytes=disk_size,
            libvirt_conn=conn,
            pool_name=preset["pool"],
            source_name=kwargs.get("src", None),
            source_pool_name=kwargs.get("src-pool", None),
        )

        boot_order = int(kwargs["boot"]) if "boot" in kwargs else None
        d.add_disk(
            v,
            bus=preset["bus"],
            cache=preset["cache"],
            boot_order=boot_order,
        )

    if seed_disk is not None:

        v = Volume(
            f"{args.name}-seed",
            create_size_bytes=seed_disk["size"],
            libvirt_conn=conn,
            pool_name=seed_disk["preset"]["pool"],
        )

        v.upload(seed_disk["fp"], seed_disk["size"])

        d.add_disk(
            v,
            bus=seed_disk["preset"]["bus"],
            cache=seed_disk["preset"]["cache"],
        )

    for preset, kwargs in nics:
        mac_address = kwargs.get("mac", None)
        boot_order = int(kwargs["boot"]) if "boot" in kwargs else None
        if "network" in preset:
            d.add_network_interface(
                preset["network"],
                model_type=preset["type"],
                mac_address=mac_address,
                boot_order=boot_order,
            )
        elif "bridge" in preset:
            d.add_bridge_interface(
                preset["bridge"],
                model_type=preset["type"],
                mac_address=mac_address,
                boot_order=boot_order,
            )
        else:
            raise CliError(f"Preset {preset_name} is invalid")

    d.define()

    # TODO: Output UUID


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
        elif args.command == "create":
            cmd_create(args, config)
    except CliError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
