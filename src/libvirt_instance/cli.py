import argparse
import importlib.metadata
import logging
import sys
from pathlib import Path

import libvirt  # type: ignore

from libvirt_instance import util
from libvirt_instance.config import load_config
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

    parser_version = subparsers.add_parser("version", help="show version")

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

    return parser.parse_args()


def cmd_create(args: argparse.Namespace, config: dict):
    cpu_model = args.cpu_model or config["defaults"].get("cpu-model", None)
    arch_name = args.arch_name or config["defaults"].get("arch-name", None)
    if not arch_name:
        raise CliError("Please provide architecture name")
    machine_type = args.machine_type or config["defaults"].get("machine-type", None)
    if not machine_type:
        raise CliError("Please provide machine type")
    domain_type = args.domain_type or config["defaults"].get("domain-type", None)
    if not domain_type:
        raise CliError("Please provide domain type")
    domain_preset = args.domain_preset or config["defaults"].get("domain-preset", None)
    if not domain_preset:
        raise CliError("Please select a domain preset to base the VM on")

    # Check if preset names are valid before performing any actions.
    if domain_preset not in config["preset"]["domain"]:
        raise CliError(f"Domain preset {domain_preset} not found in the config")
    for preset_name, _, _ in args.disk:
        if preset_name not in config["preset"]["disk"]:
            raise CliError(f"Disk preset {preset_name} not found in the config")

    for preset_name, _ in args.nic:
        if preset_name not in config["preset"]["interface"]:
            raise CliError(f"Interface preset {preset_name} not found in the config")

    conn = libvirt.open(args.connect)

    d = DomainDefinition(
        args.name,
        ram_bytes=args.memory,
        vcpus=args.vcpu,
        basexml=config["preset"]["domain"][domain_preset]["xml"],
        libvirt_conn=conn,
        domain_type=domain_type,
        machine=machine_type,
        arch_name=arch_name,
        cpu_model=cpu_model,
    )

    for i, (preset_name, disk_size, kwargs) in enumerate(args.disk):
        preset = config["preset"]["disk"][preset_name]

        v = Volume(
            f"{args.name}-disk{i}",
            create_size_bytes=disk_size,
            libvirt_conn=conn,
            pool_name=preset["pool"],
        )

        d.add_disk(
            v,
            bus=preset["bus"],
            cache=preset["cache"],
            boot_order=kwargs.get("boot", None),
        )

    for preset_name, kwargs in args.nic:
        preset = config["preset"]["interface"][preset_name]

        if "network" in preset:
            d.add_network_interface(
                preset["network"],
                model_type=preset["type"],
                mac_address=kwargs.get("mac", None),
                boot_order=kwargs.get("boot", None),
            )
        elif "bridge" in preset:
            d.add_bridge_interface(
                preset["bridge"],
                model_type=preset["type"],
                mac_address=kwargs.get("mac", None),
                boot_order=kwargs.get("boot", None),
            )
        else:
            raise CliError(f"Preset {preset_name} is invalid")

    d.define()


def main() -> None:

    args = parse_args()

    logging.basicConfig(level=args.log_level)

    config = load_config(args.config_file)

    try:
        if args.command == "version":
            print(importlib.metadata.version("libvirt-instance"))
        elif args.command == "create":
            cmd_create(args, config)
    except CliError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
