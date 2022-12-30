# MIT license
# Copyright 2022 Sergej Alikov <sergej.alikov@gmail.com>

import logging
import xml.etree.ElementTree as ET
from typing import Any, BinaryIO, Optional

import libvirt  # type: ignore

from libvirt_instance.util import index_to_drive_name

logger = logging.getLogger(__name__)

DISK_BUS_VIRTIO = "virtio"
DISK_BUS_SCSI = "scsi"

DISK_BUS_PROPERTIES: dict[str, Any] = {
    DISK_BUS_VIRTIO: {
        "dev_prefix": "vd",
        "max_nr": 32,  # https://rwmj.wordpress.com/2010/12/22/whats-the-maximum-number-of-virtio-blk-disks/
    },
    DISK_BUS_SCSI: {
        "dev_prefix": "sd",
        "max_nr": 1024,  # Technically more than 1024, but https://rwmj.wordpress.com/2017/04/25/how-many-disks-can-you-add-to-a-virtual-linux-machine/
    },
}


class InvalidBaseXmlError(Exception):
    pass


class UnsupportedVolumeTypeError(Exception):
    pass


class UnsupportedBusError(Exception):
    pass


class VolumeAlreadyExistsError(Exception):
    pass


class SourceVolumeTooBigError(Exception):
    pass


class Volume:
    def __init__(
        self,
        name: str,
        *,
        create_size_bytes: int,
        pool_name: str,
        exist_ok: bool = False,
        libvirt_conn: libvirt.virConnect,
        source_pool_name: Optional[str] = None,
        source_name: Optional[str] = None,
    ) -> None:

        alignment_remainder = create_size_bytes % (2**20)
        if alignment_remainder == 0:
            volume_size_bytes = create_size_bytes
        else:
            volume_size_bytes = create_size_bytes + (2**20 - alignment_remainder)
            logger.debug(
                f"Padding target volume {name} size from requested {create_size_bytes} "
                f"bytes to {volume_size_bytes} bytes for 1MiB alignment"
            )

        self._conn = libvirt_conn

        self.name = name

        self.pool = self._conn.storagePoolLookupByName(pool_name)

        pool_el = ET.fromstring(self.pool.XMLDesc())

        self.pool_type = pool_el.get("type")

        if name in set(self.pool.listVolumes()):
            if not exist_ok:
                raise VolumeAlreadyExistsError(
                    f"Volume {name} already exists in the {pool_name} pool."
                )

            logger.debug(f"Using existing volume {name}")
            self.volume = self.pool.storageVolLookupByName(name)
        else:
            volume_el = ET.Element("volume")

            ET.SubElement(volume_el, "name").text = name

            if source_name is None:
                logger.debug(f"Creating a new volume {name} from scratch")

                capacity_el = ET.SubElement(volume_el, "capacity")
                capacity_el.set("unit", "bytes")
                capacity_el.text = str(volume_size_bytes)

                allocation_el = ET.SubElement(volume_el, "allocation")
                allocation_el.set("unit", "bytes")
                allocation_el.text = str(volume_size_bytes)

                self.volume = self.pool.createXML(
                    ET.tostring(volume_el, encoding="unicode")
                )
            else:
                logger.debug(
                    f"Creating a new volume {name} using {source_name} as the base"
                )
                if source_pool_name is not None:
                    source_pool = self._conn.storagePoolLookupByName(source_pool_name)
                else:
                    source_pool = self.pool

                source_volume = source_pool.storageVolLookupByName(source_name)

                _, source_volume_capacity, _ = source_volume.info()

                if source_volume_capacity > volume_size_bytes:
                    raise SourceVolumeTooBigError(
                        f"Source volume {source_name} size {source_volume_capacity} "
                        f"is larger than the target size {volume_size_bytes} of {name}."
                    )

                self.volume = self.pool.createXMLFrom(
                    ET.tostring(volume_el, encoding="unicode"), source_volume
                )

                if source_volume_capacity < volume_size_bytes:
                    logger.debug(
                        f"Growing volume {name} to target size {volume_size_bytes} "
                        f"as the base volume {source_name} is smaller"
                    )
                    self.volume.resize(
                        volume_size_bytes, libvirt.VIR_STORAGE_VOL_RESIZE_ALLOCATE
                    )

    def upload(self, fp: BinaryIO, size: int) -> None:
        def handler(stream: libvirt.virStream, nbytes: int, fp: BinaryIO):
            logger.debug(f"Uploading chunk to volume {self.name}")
            return fp.read(nbytes)

        stream = self._conn.newStream()

        logger.debug(f"Starting upload of {size} bytes to volume {self.name}")
        self.volume.upload(stream, 0, size)

        stream.sendAll(handler, fp)

        stream.finish()
        logger.debug(f"Upload to volume {self.name} finished")


class DomainDefinition:
    def __init__(
        self,
        name: str,
        *,
        ram_bytes: int,
        vcpus: int,
        basexml: str,
        libvirt_conn: libvirt.virConnect,
        domain_type: str = "kvm",
        machine: str = "pc",
        uuid: Optional[str] = None,
        arch_name: Optional[str] = None,
        cpu_model: Optional[str] = None,
    ) -> None:

        self._conn = libvirt_conn
        self._domain_el = ET.fromstring(basexml)

        caps = self._conn.getCapabilities()
        self._caps_el = ET.fromstring(caps)

        if self._domain_el.tag != "domain":
            raise InvalidBaseXmlError("The root of the base XML must be <domain>.")

        self._domain_el.set("type", domain_type)

        if arch_name is None:
            arch_el = self._caps_el.find("./host/cpu/arch")
            if arch_el is not None:
                if arch_el.text is not None:
                    arch_name = arch_el.text

        if arch_name is None:
            raise RuntimeError("Unable to get target arch name")

        if uuid is not None:

            uuid_el = self._domain_el.find("./uuid")
            if uuid_el is None:
                uuid_el = ET.SubElement(self._domain_el, "uuid")
            uuid_el.text = uuid

        os_el = self._domain_el.find("./os")
        if os_el is None:
            os_el = ET.SubElement(self._domain_el, "os")

        os_type_el = os_el.find("./type")
        if os_type_el is not None:
            os_el.remove(os_type_el)
        os_type_el = ET.SubElement(os_el, "type")
        os_type_el.set("arch", arch_name)
        os_type_el.set("machine", machine)
        os_type_el.text = "hvm"

        cpu_el = self._domain_el.find("cpu")

        if cpu_model is None:
            if cpu_el is None:
                cpu_el = ET.SubElement(self._domain_el, "cpu")
                cpu_el.set("mode", "host-passthrough")
                cpu_el.set("check", "none")
                cpu_el.set("migratable", "on")
        else:
            if cpu_el is not None:
                self._domain_el.remove(cpu_el)

            cpu_el = ET.SubElement(self._domain_el, "cpu")
            cpu_el.set("mode", "custom")
            cpu_el.set("match", "exact")

            cpu_model_el = ET.SubElement(cpu_el, "model")
            cpu_model_el.set("fallback", "allow")
            cpu_model_el.text = cpu_model

        for el_name in ("name", "memory", "currentMemory", "vcpu"):
            el = self._domain_el.find(el_name)
            if el is not None:
                self._domain_el.remove(el)

        ET.SubElement(self._domain_el, "name").text = name

        memory_el = ET.SubElement(self._domain_el, "memory")
        memory_el.set("unit", "bytes")
        memory_el.text = str(ram_bytes)

        vcpu_el = ET.SubElement(self._domain_el, "vcpu")
        vcpu_el.set("placement", "static")
        vcpu_el.text = str(vcpus)

        devices_el = self._domain_el.find("./devices")
        if devices_el is None:
            devices_el = ET.SubElement(self._domain_el, "devices")

        self._devices_el = devices_el

        emulator_el = self._devices_el.find("./emulator")
        if emulator_el is None:
            emulator_el = ET.SubElement(self._devices_el, "emulator")
        emulator_el.text = self._get_emulator(domain_type, arch_name, machine)

    def __str__(self) -> str:
        return ET.tostring(self._domain_el, encoding="unicode")

    def _get_emulator(self, domain_type, arch_name, machine) -> str:
        guest_caps_els = self._caps_el.findall("./guest")

        if guest_caps_els is None:
            raise RuntimeError("No guest capabilities found.")

        for guest_caps_el in guest_caps_els:
            os_type_el = guest_caps_el.find("./os_type")
            if os_type_el is None:
                continue
            if os_type_el.text != "hvm":
                continue

            arch_els = guest_caps_el.findall(
                f"./arch[@name='{arch_name}']/domain[@type='{domain_type}']/.."
            )
            if arch_els is None:
                continue

            for arch_el in arch_els:
                domain_machine_el = arch_el.find(
                    f"./domain[@type='{domain_type}']/machine[.='{machine}']"
                )
                if domain_machine_el is None:
                    machine_el = arch_el.find(f"./machine[.='{machine}']")
                    if machine_el is None:
                        continue

                domain_emulator_el = arch_el.find(
                    f"./domain[@type='{domain_type}']/emulator"
                )
                if domain_emulator_el is not None:
                    if domain_emulator_el.text is not None:
                        return domain_emulator_el.text

                arch_emulator_el = arch_el.find("./emulator")
                if arch_emulator_el is not None:
                    if arch_emulator_el.text is not None:
                        return arch_emulator_el.text

                raise RuntimeError("Found architecture is missing emulator")

        raise RuntimeError(
            "Unable to find a suitable guest architecture in capabilities"
        )

    @property
    def name(self):
        return self._domain_el.find("name").text

    @property
    def memory(self):
        return int(self._domain_el.find("memory").text)

    @property
    def vcpu(self):
        return int(self._domain_el.find("vcpu").text)

    def define(self):
        self._conn.defineXML(str(self))

    def _used_scsi_addresses(self) -> dict[int, dict[int, dict[int, set]]]:
        used_addresses: dict[int, dict[int, dict[int, set]]] = {}

        for disk_el in self._devices_el.findall("./disk/target[@bus='scsi']/.."):

            address_el = disk_el.find("./address[@type='drive']")
            if address_el is None:
                raise RuntimeError("SCSI disk is missing an address attribute")

            controller_attr = address_el.get("controller")
            if controller_attr is None:
                raise RuntimeError(
                    "SCSI disk address is missing a controller attribute"
                )
            controller = int(controller_attr)

            bus_attr = address_el.get("bus")
            if bus_attr is None:
                raise RuntimeError("SCSI disk address is missing a bus attribute")
            bus = int(bus_attr)

            target_attr = address_el.get("target")
            if target_attr is None:
                raise RuntimeError("SCSI disk address is missing a target attribute")
            target = int(target_attr)

            unit_attr = address_el.get("unit")
            if unit_attr is None:
                raise RuntimeError("SCSI disk address is missing a unit attribute")
            unit = int(unit_attr)

            if controller not in used_addresses:
                used_addresses[controller] = {}

            if bus not in used_addresses[controller]:
                used_addresses[controller][bus] = {}

            if target not in used_addresses[controller][bus]:
                used_addresses[controller][bus][target] = set()

            used_addresses[controller][bus][target].add(unit)

        return used_addresses

    def _allocate_scsi_address(self) -> tuple[int, int, int, int]:

        used_addresses = self._used_scsi_addresses()

        controller_els = self._devices_el.findall(
            "./controller[@type='scsi'][@model='virtio-scsi']"
        )

        # bus is limited to a single 0
        bus = 0

        for controller_el in controller_els:
            index_attr = controller_el.get("index") or "0"
            controller = int(index_attr)
            for target in range(256):
                for unit in range(16384):
                    if unit not in used_addresses.get(controller, {}).get(bus, {}).get(
                        target, set()
                    ):
                        break
                else:
                    continue

                break
            else:
                continue

            break
        else:  # No room found on existing controllers.
            if len(controller_els) < 32:
                controller = len(controller_els)
                controller_el = ET.SubElement(self._devices_el, "controller")
                controller_el.set("type", "scsi")
                controller_el.set("model", "virtio-scsi")
                controller_el.set("index", str(controller))
                target = 0
                unit = 0
            else:
                # 256 * 16384 = 4194304, yeah, right :)
                raise RuntimeError("All available SCSI controllers are full.")

        return controller, bus, target, unit

    # TODO: Function too long, needs refactor.
    def add_disk(
        self,
        volume: Volume,
        *,
        bus: str = DISK_BUS_VIRTIO,
        cache: str = "none",
        discard: Optional[str] = None,
        boot_order: Optional[int] = None,
    ) -> None:

        try:
            bus_type_properties = DISK_BUS_PROPERTIES[bus]
        except KeyError:
            raise UnsupportedBusError(f"Unsupported bus {bus}")

        disk_el = ET.Element("disk")

        if volume.pool_type in ("dir", "logical"):
            disk_el.set("type", "volume")
            disk_el.set("device", "disk")

            source_el = ET.SubElement(disk_el, "source")
            source_el.set("pool", volume.pool.name())
            source_el.set("volume", volume.volume.name())
        elif volume.pool_type == "rbd":
            disk_el.set("type", "network")
            disk_el.set("device", "disk")

            pool_el = ET.fromstring(volume.pool.XMLDesc())
            volume_el = ET.fromstring(volume.volume.XMLDesc())

            volume_path_el = volume_el.find("./target/path")
            if volume_path_el is not None:
                path = volume_path_el.text
            else:
                path = None

            if path is None:
                raise RuntimeError(
                    "Volume {} is missing path".format(volume.volume.name())
                )

            source_el = ET.SubElement(disk_el, "source")
            source_el.set("protocol", "rbd")
            source_el.set("name", path)

            for host_el in pool_el.findall("./source/host"):
                name = host_el.get("name")
                port = host_el.get("port")

                if name is not None:
                    source_host_el = ET.SubElement(source_el, "host")
                    source_host_el.set("name", name)
                    if port is not None:
                        source_host_el.set("port", port)

            pool_source_auth_el = pool_el.find("./source/auth[@type='ceph']")
            if pool_source_auth_el is not None:
                auth_username = pool_source_auth_el.get("username")

                pool_source_auth_secret_el = pool_source_auth_el.find("./secret")
                if pool_source_auth_secret_el is not None:
                    auth_secret_uuid = pool_source_auth_secret_el.get("uuid")
                else:
                    auth_secret_uuid = None

                if auth_username and auth_secret_uuid:
                    auth_el = ET.SubElement(source_el, "auth")
                    auth_el.set("username", auth_username)
                    auth_secret_el = ET.SubElement(auth_el, "secret")
                    auth_secret_el.set("type", "ceph")
                    auth_secret_el.set("uuid", auth_secret_uuid)

        else:
            raise UnsupportedVolumeTypeError()

        dev_prefix = bus_type_properties["dev_prefix"]
        max_nr = bus_type_properties["max_nr"]

        existing_target_devices = []

        for target_el in self._devices_el.findall(f"./disk/target[@bus='{bus}']"):

            target_dev = target_el.get("dev")
            if target_dev is None:
                continue

            if not target_dev.startswith(dev_prefix):
                continue

            existing_target_devices.append(target_dev)

        for dev_nr in range(max_nr):
            drive_name = index_to_drive_name(dev_nr)
            dev = f"{dev_prefix}{drive_name}"

            if dev in existing_target_devices:
                continue

            break
        else:
            raise RuntimeError(
                f"All of {max_nr} possible disk devices are already used on the {bus} bus."
            )

        target_el = ET.SubElement(disk_el, "target")
        target_el.set("dev", dev)
        target_el.set("bus", bus)

        driver_el = ET.SubElement(disk_el, "driver")
        driver_el.set("name", "qemu")
        driver_el.set("type", "raw")
        driver_el.set("cache", cache)
        if discard is not None:
            driver_el.set("discard", discard)

        if boot_order is not None:
            boot_el = ET.SubElement(disk_el, "boot")
            boot_el.set("order", str(boot_order))

        if bus == DISK_BUS_SCSI:
            (
                scsi_controller,
                scsi_bus,
                scsi_target,
                scsi_unit,
            ) = self._allocate_scsi_address()
            address_el = ET.SubElement(disk_el, "address")
            address_el.set("type", "drive")
            address_el.set("controller", str(scsi_controller))
            address_el.set("bus", str(scsi_bus))
            address_el.set("target", str(scsi_target))
            address_el.set("unit", str(scsi_unit))

        # TODO: Autogenerate disk serial numbers?

        self._devices_el.append(disk_el)

    def _add_generic_interface(
        self,
        *,
        model_type: str = "virtio",
        mac_address: Optional[str] = None,
        boot_order: Optional[int] = None,
        mtu: Optional[int] = None,
    ) -> ET.Element:
        interface_el = ET.SubElement(self._devices_el, "interface")

        model_el = ET.SubElement(interface_el, "model")
        model_el.set("type", model_type)

        if mtu is not None:
            mtu_el = ET.SubElement(interface_el, "mtu")
            mtu_el.set("size", str(mtu))

        if mac_address is not None:
            mac_el = ET.SubElement(interface_el, "mac")
            mac_el.set("address", mac_address)

        if boot_order is not None:
            boot_el = ET.SubElement(interface_el, "boot")
            boot_el.set("order", str(boot_order))

        return interface_el

    def add_bridge_interface(self, source_bridge: str, **kwargs) -> None:

        interface_el = self._add_generic_interface(**kwargs)

        interface_el.set("type", "bridge")

        source_el = ET.SubElement(interface_el, "source")
        source_el.set("bridge", source_bridge)

    def add_network_interface(
        self,
        source_network: str = "default",
        **kwargs,
    ) -> None:

        interface_el = self._add_generic_interface(**kwargs)

        interface_el.set("type", "network")

        source_el = ET.SubElement(interface_el, "source")
        source_el.set("network", source_network)
