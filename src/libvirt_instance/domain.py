import pathlib
import xml.etree.ElementTree as ET
from typing import Optional

import libvirt  # type: ignore
from typing_extensions import TypedDict

from libvirt_instance.util import index_to_drive_name

DISK_BUS_VIRTIO = "virtio"
DISK_BUS_SCSI = "scsi"

DiskBusProperties = TypedDict("DiskBusProperties", {"dev_prefix": str, "max_nr": int})
DISK_BUS_PROPERTIES: dict[str, DiskBusProperties] = {
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


class UnsupportedPoolTypeError(Exception):
    pass


class UnsupportedVolumeTypeError(Exception):
    pass


class UnsupportedBusError(Exception):
    pass


class VolumeAlreadyExistsError(Exception):
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
    ) -> None:

        self.name = name

        self.pool = libvirt_conn.storagePoolLookupByName(pool_name)

        pool_el = ET.fromstring(self.pool.XMLDesc())

        self.pool_type = pool_el.get("type")

        if self.pool_type == "dir":
            if name in set(self.pool.listVolumes()):
                if not exist_ok:
                    raise VolumeAlreadyExistsError(
                        f"Volume {name} already exists in the {pool_name} pool."
                    )

                self.volume = self.pool.storageVolLookupByName(name)
            else:
                volume_el = ET.Element("volume")
                volume_el.set("type", "file")

                ET.SubElement(volume_el, "name").text = name
                capacity_el = ET.SubElement(volume_el, "capacity")
                capacity_el.set("unit", "bytes")
                capacity_el.text = str(create_size_bytes)

                allocation_el = ET.SubElement(volume_el, "allocation")
                allocation_el.set("unit", "bytes")
                allocation_el.text = str(create_size_bytes)

                pool_target_path = pool_el.find("./target/path")
                if pool_target_path is not None and pool_target_path.text is not None:
                    vol_path = pathlib.Path(pool_target_path.text).joinpath(name)
                else:
                    raise RuntimeError(
                        f"Invalid pool {pool_name} - missing target/path."
                    )

                target_el = ET.SubElement(volume_el, "target")
                ET.SubElement(target_el, "path").text = str(vol_path)
                ET.SubElement(target_el, "format").set("type", "raw")

                self.volume = self.pool.createXML(
                    ET.tostring(volume_el, encoding="unicode")
                )


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

        domain_arch_name: str

        if arch_name is None:
            arch_el = self._caps_el.find("./host/cpu/arch")
            if arch_el is not None:
                if arch_el.text is not None:
                    arch_name = arch_el.text

        if arch_name is None:
            raise RuntimeError("Unable to get target arch name")

        os_el = self._domain_el.find("./os") or ET.SubElement(self._domain_el, "os")

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
            cpu_el.set("check", "partial")

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

        self._devices_el = self._domain_el.find("./devices") or ET.SubElement(
            self._domain_el, "devices"
        )

        emulator_el = self._devices_el.find("./emulator") or ET.SubElement(
            self._devices_el, "emulator"
        )
        emulator_el.text = self._get_emulator(domain_type, arch_name, machine)

    def __str__(self) -> str:
        return ET.tostring(self._domain_el, encoding="unicode")

    def _get_emulator(self, domain_type, arch_name, machine) -> str:
        guest_caps_els = self._caps_el.findall(f"./guest")

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

        dev_prefix = bus_type_properties["dev_prefix"]
        max_nr = bus_type_properties["max_nr"]

        existing_disk_els = []
        existing_target_devices = []

        for e_disk_el in self._devices_el.findall(f"./disk"):

            target_el = e_disk_el.find("./target")
            if target_el is None:
                continue

            target_dev = target_el.get("dev")
            if target_dev is None:
                continue

            target_bus = target_el.get("bus")

            if target_bus is not None:
                if target_bus != bus:
                    continue
            else:
                if not target_dev.startswith(dev_prefix):
                    continue

            existing_disk_els.append(e_disk_el)
            existing_target_devices.append(target_dev)

        if bus == DISK_BUS_SCSI:

            existing_addresses: dict[int, dict[int, dict[int, set]]] = {}
            for e_disk_el in existing_disk_els:

                e_address_el = e_disk_el.find("./address[@type='drive']")
                if e_address_el is None:
                    raise RuntimeError("SCSI disk is missing the address attribute")

                controller_attr = e_address_el.get("controller")
                if controller_attr is None:
                    raise RuntimeError(
                        "SCSI disk address is missing the controller attribute"
                    )
                e_scsi_controller = int(controller_attr)

                bus_attr = e_address_el.get("bus")
                if bus_attr is None:
                    raise RuntimeError("SCSI disk address is missing the bus attribute")
                e_scsi_bus = int(bus_attr)

                target_attr = e_address_el.get("target")
                if target_attr is None:
                    raise RuntimeError(
                        "SCSI disk address is missing the target attribute"
                    )
                e_scsi_target = int(target_attr)

                unit_attr = e_address_el.get("unit")
                if unit_attr is None:
                    raise RuntimeError(
                        "SCSI disk address is missing the unit attribute"
                    )
                e_scsi_unit = int(unit_attr)

                if e_scsi_controller not in existing_addresses:
                    existing_addresses[e_scsi_controller] = {}

                if e_scsi_bus not in existing_addresses[e_scsi_controller]:
                    existing_addresses[e_scsi_controller][e_scsi_bus] = {}

                if (
                    e_scsi_target
                    not in existing_addresses[e_scsi_controller][e_scsi_bus]
                ):
                    existing_addresses[e_scsi_controller][e_scsi_bus][
                        e_scsi_target
                    ] = set()

                existing_addresses[e_scsi_controller][e_scsi_bus][e_scsi_target].add(
                    e_scsi_unit
                )

            controller_els = self._devices_el.findall(
                "./controller[@type='scsi'][@model='virtio-scsi']"
            )

            need_new_controller = False

            # bus is limited to a single 0
            scsi_bus = 0

            for controller_el in controller_els:
                index_attr = controller_el.get("index") or "0"
                scsi_controller = int(index_attr)
                for scsi_target in range(256):
                    for scsi_unit in range(16384):
                        if scsi_unit not in existing_addresses.get(
                            scsi_controller, {}
                        ).get(scsi_bus, {}).get(scsi_target, set()):
                            break
                    else:
                        continue

                    break
                else:
                    continue

                break
            else:
                if len(controller_els) < 32:
                    need_new_controller = True
                    scsi_controller = len(controller_els)
                else:
                    # 256 * 16384 = 4194304, yeah, right :)
                    raise RuntimeError("All available SCSI controllers are full.")

            if need_new_controller:
                controller_el = ET.SubElement(self._devices_el, "controller")
                controller_el.set("type", "scsi")
                controller_el.set("model", "virtio-scsi")
                controller_el.set("index", str(scsi_controller))
                scsi_target = 0
                scsi_unit = 0

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

        if volume.pool_type == "dir":
            disk_el = ET.SubElement(self._devices_el, "disk")

            disk_el.set("type", "volume")
            disk_el.set("device", "disk")

            source_el = ET.SubElement(disk_el, "source")
            source_el.set("pool", volume.pool.name())
            source_el.set("volume", volume.volume.name())

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
                address_el = ET.SubElement(disk_el, "address")
                address_el.set("type", "drive")
                address_el.set("controller", str(scsi_controller))
                address_el.set("bus", str(scsi_bus))
                address_el.set("target", str(scsi_target))
                address_el.set("unit", str(scsi_unit))

        else:
            raise UnsupportedVolumeTypeError()

        # TODO: Autogenerate disk serial numbers?

    def _add_generic_interface(
        self,
        *,
        model_type: str = "virtio",
        mac_address: Optional[str] = None,
        boot_order: Optional[int] = None,
    ) -> ET.Element:
        interface_el = ET.SubElement(self._devices_el, "interface")

        model_el = ET.SubElement(interface_el, "model")
        model_el.set("type", model_type)

        if mac_address is not None:
            mac_el = ET.SubElement(interface_el, "mac")
            mac_el.set("address", mac_address)

        if boot_order is not None:
            boot_el = ET.SubElement(interface_el, "boot")
            boot_el.set("order", str(boot_order))

        return interface_el

    def add_bridge_interface(
        self,
        source_bridge: str,
        *,
        model_type: str = "virtio",
        mac_address: Optional[str] = None,
        boot_order: Optional[int] = None,
    ) -> None:

        interface_el = self._add_generic_interface(
            model_type=model_type, mac_address=mac_address, boot_order=boot_order
        )

        interface_el.set("type", "bridge")

        source_el = ET.SubElement(interface_el, "source")
        source_el.set("bridge", source_bridge)

    def add_network_interface(
        self,
        source_network: str = "default",
        *,
        model_type: str = "virtio",
        mac_address: Optional[str] = None,
        boot_order: Optional[int] = None,
    ) -> None:

        interface_el = self._add_generic_interface(
            model_type=model_type, mac_address=mac_address, boot_order=boot_order
        )

        interface_el.set("type", "network")

        source_el = ET.SubElement(interface_el, "source")
        source_el.set("network", source_network)