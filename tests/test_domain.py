import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from libvirt_instance import domain

from .libvirt_mock import virConnect


def test_volume():
    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=virConnect(),
        pool_name="default",
    )

    assert v.volume.name() == "testvolume"


def test_volume_size_no_alignment_needed():
    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=virConnect(),
        pool_name="default",
    )

    assert v.volume.name() == "testvolume"

    volume_el = ET.fromstring(v.volume.XMLDesc())

    assert int(volume_el.find("./capacity").text) == 16777216


def test_volume_size_alignment_needed():
    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777210,
        libvirt_conn=virConnect(),
        pool_name="default",
    )

    assert v.volume.name() == "testvolume"

    volume_el = ET.fromstring(v.volume.XMLDesc())

    assert int(volume_el.find("./capacity").text) == 16777216


def test_volume_existing():
    conn = virConnect()

    domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    with pytest.raises(domain.VolumeAlreadyExistsError):
        domain.Volume(
            "testvolume",
            create_size_bytes=16777216,
            libvirt_conn=conn,
            pool_name="default",
        )


def test_volume_existing_ok():
    conn = virConnect()

    domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
        exist_ok=True,
    )

    assert v.volume.name() == "testvolume"


def test_volume_from_source():
    conn = virConnect()

    domain.Volume(
        "testvolume1",
        create_size_bytes=100000,
        libvirt_conn=conn,
        pool_name="default",
    )

    v = domain.Volume(
        "testvolume2",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
        source_name="testvolume1",
    )

    assert v.volume.name() == "testvolume2"


def test_domain_init():
    domainxml = """
    <domain>
      <name>test</name>
      <memory>12345></memory>
      <vcpu>2</vcpu>
    </domain>
    """

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))
    os_type_el = domain_el.find("./os/type")
    cpu_el = domain_el.find("./cpu")
    devices_emulator_el = domain_el.find("./devices/emulator")

    assert d.name == "foo"
    assert d.memory == 16777216
    assert d.vcpu == 1
    assert domain_el.get("type") == "kvm"
    assert os_type_el.get("arch") == "x86_64"
    assert os_type_el.get("machine") == "pc"
    assert os_type_el.text == "hvm"
    assert cpu_el.get("mode") == "host-passthrough"
    assert cpu_el.get("check") == "none"
    assert devices_emulator_el.text == "/usr/bin/qemu-kvm"


def test_domain_existing_devices():
    domainxml = """
    <domain>
      <devices></devices>
    </domain>
    """

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))

    # Check if we've added the emulator element to the existing the <devices> and
    # not into additional one.
    devices_el = domain_el.find("./devices")
    devices_emulator_el = devices_el.find("./emulator")

    assert devices_emulator_el.text == "/usr/bin/qemu-kvm"


def test_domain_existing_devices_emulator():
    domainxml = """
    <domain>
      <devices><emulator>/dev/null</emulator></devices>
    </domain>
    """

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))

    # Check if we've modified the existing emulator element and
    # not an additional one.
    devices_el = domain_el.find("./devices")
    devices_emulator_el = devices_el.find("./emulator")

    assert devices_emulator_el.text == "/usr/bin/qemu-kvm"


def test_domain_define():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
    )

    d.define()

    assert "foo" in conn._domains


def test_domain_init_uuid():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        uuid="a009bdf8-a172-4d63-9164-625b77f40ac4",
    )

    domain_el = ET.fromstring(str(d))
    uuid_el = domain_el.find("./uuid")

    assert uuid_el.text == "a009bdf8-a172-4d63-9164-625b77f40ac4"


def test_domain_init_override_existing_uuid():
    domainxml = """
    <domain>
      <uuid>80247a17-1bf4-4c9f-b243-564e8ac32d6d</uuid>
    </domain>
    """

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        uuid="a009bdf8-a172-4d63-9164-625b77f40ac4",
    )

    domain_el = ET.fromstring(str(d))
    uuid_el = domain_el.find("./uuid")

    assert uuid_el.text == "a009bdf8-a172-4d63-9164-625b77f40ac4"


def test_domain_init_host_arch():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))
    os_type_el = domain_el.find("./os/type")

    assert os_type_el.get("arch") == "x86_64"


def test_domain_init_existing_os():
    domainxml = "<domain><os firmware='efi'></os></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))
    os_el = domain_el.find("./os")

    assert os_el.get("firmware") == "efi"
    # Check if we've added the type element to the existing the <os> and
    # not into additional one.
    assert os_el.find("./type") is not None


def test_domain_init_domain_type_specific_machine():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc-i440fx-7.0",
    )

    domain_el = ET.fromstring(str(d))
    os_type_el = domain_el.find("./os/type")

    assert os_type_el.get("arch") == "x86_64"


def test_domain_init_domain_type_specific_machine_wrong_domain_type():
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=virConnect(),
            basexml=domainxml,
            domain_type="kvm",
            arch_name="x86_64",
            machine="pc-i440fx-6.1",
        )


def test_domain_init_custom_domain_type():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="qemu",
        arch_name="x86_64",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))

    assert domain_el.get("type") == "qemu"


def test_domain_init_unsupported_domain_type():
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=virConnect(),
            basexml=domainxml,
            domain_type="UNSUPPORTED",
            arch_name="x86_64",
            machine="pc",
        )


def test_domain_init_custom_cpu():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
        cpu_model="SandyBridge",
    )

    domain_el = ET.fromstring(str(d))
    cpu_el = domain_el.find("./cpu")
    cpu_model_el = cpu_el.find("./model")

    assert cpu_el.get("mode") == "custom"
    assert cpu_el.get("match") == "exact"
    assert cpu_el.get("check") == "partial"

    assert cpu_model_el.text == "SandyBridge"
    assert cpu_model_el.get("fallback") == "allow"


def test_domain_init_existing_cpu():
    domainxml = "<domain><cpu><model>TestCPU</model></cpu></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))
    cpu_model_el = domain_el.find("./cpu/model")

    assert cpu_model_el.text == "TestCPU"


def test_domain_init_existing_cpu_override():
    domainxml = "<domain><cpu><model>TestCPU</model></cpu></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
        cpu_model="SandyBridge",
    )

    domain_el = ET.fromstring(str(d))
    cpu_model_el = domain_el.find("./cpu/model")

    assert cpu_model_el.text == "SandyBridge"


def test_domain_init_unsupported_arch():
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=virConnect(),
            basexml=domainxml,
            domain_type="kvm",
            arch_name="INVALID",
            machine="pc",
        )


def test_domain_init_unsupported_machine():
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=virConnect(),
            basexml=domainxml,
            domain_type="kvm",
            arch_name="x86_64",
            machine="INVALID",
        )


def test_domain_add_disk_virtio_blk():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    d.add_disk(v, bus="virtio", cache="none")

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    assert disk_el.get("type") == "volume"
    assert disk_el.get("device") == "disk"

    assert disk_el.find("./boot") is None

    assert disk_el.find("./target").get("dev") == "vda"
    assert disk_el.find("./target").get("bus") == "virtio"

    assert disk_el.find("./source").get("pool") == "default"
    assert disk_el.find("./source").get("volume") == "testvolume"

    assert disk_el.find("./driver").get("cache") == "none"


def test_domain_add_disk_virtio_scsi():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    d.add_disk(v, bus="scsi", cache="none")

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    target_el = disk_el.find("./target")
    assert target_el.get("dev") == "sda"
    assert target_el.get("bus") == "scsi"

    source_el = disk_el.find("./source")
    assert source_el.get("pool") == "default"
    assert source_el.get("volume") == "testvolume"

    assert disk_el.find("./driver").get("cache") == "none"

    address_el = disk_el.find("./address")
    assert address_el.get("controller") == "0"
    assert address_el.get("bus") == "0"
    assert address_el.get("target") == "0"
    assert address_el.get("unit") == "0"

    controller_el = domain_el.find(
        "./devices/controller[@type='scsi'][@model='virtio-scsi'][@index='0']"
    )

    assert controller_el is not None


def test_domain_add_disk_virtio_scsi_existing_controller():
    domainxml = """
    <domain>
      <devices>
        <controller type="scsi" model="virtio-scsi" index='3'>
          <alias name='scsi0'/>
          <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>
        </controller>
      </devices>
    </domain>
    """

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    d.add_disk(v, bus="scsi", cache="none")

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    address_el = disk_el.find("./address")
    assert address_el.get("controller") == "3"
    assert address_el.get("bus") == "0"
    assert address_el.get("target") == "0"
    assert address_el.get("unit") == "0"


def test_domain_add_disk_multiple():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v1 = domain.Volume(
        "v1",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    v2 = domain.Volume(
        "v2",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    v3 = domain.Volume(
        "v3",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    d.add_disk(v1, bus="virtio", cache="none")
    d.add_disk(v2, bus="virtio", cache="none")
    d.add_disk(v3, bus="scsi", cache="none")

    domain_el = ET.fromstring(str(d))

    disk_els = domain_el.findall("./devices/disk")

    assert len(disk_els) == 3

    assert disk_els[0].find("./target").get("dev") == "vda"
    assert disk_els[1].find("./target").get("dev") == "vdb"
    assert disk_els[2].find("./target").get("dev") == "sda"


def test_domain_add_disk_multiple_scsi():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v1 = domain.Volume(
        "v1",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    v2 = domain.Volume(
        "v2",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    d.add_disk(v1, bus="scsi", cache="none")
    d.add_disk(v2, bus="scsi", cache="none")

    domain_el = ET.fromstring(str(d))

    disk_els = domain_el.findall("./devices/disk")

    assert len(disk_els) == 2

    assert disk_els[0].find("./target").get("dev") == "sda"
    assert disk_els[1].find("./target").get("dev") == "sdb"

    assert disk_els[0].find("./address").get("unit") == "0"
    assert disk_els[1].find("./address").get("unit") == "1"


def test_domain_add_disk_discard():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    d.add_disk(v, discard="unmap")

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    assert disk_el.find("./driver").get("discard") == "unmap"


def test_domain_add_disk_boot_order():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    d.add_disk(v, boot_order=1)

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    assert disk_el.find("./boot").get("order") == "1"


def test_domain_add_disk_unsupported_bus():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="default",
    )

    with pytest.raises(domain.UnsupportedBusError):
        d.add_disk(v, bus="UNSUPPORTED BUS")


def test_domain_add_disk_unsupported_volume_type():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
    )

    v = MagicMock()
    v.pool_type = "UNSUPPORTED"

    with pytest.raises(domain.UnsupportedVolumeTypeError):
        d.add_disk(v)


def test_domain_add_disk_rbd():
    domainxml = "<domain></domain>"

    conn = virConnect()

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=conn,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=conn,
        pool_name="ceph",
    )

    d.add_disk(v)

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")
    source_el = disk_el.find("./source")
    source_host_els = source_el.findall("./host")
    auth_el = source_el.find("./auth")
    auth_secret_el = auth_el.find("./secret")

    assert disk_el is not None

    assert disk_el.get("type") == "network"
    assert disk_el.get("device") == "disk"

    assert source_el.get("protocol") == "rbd"
    assert source_el.get("name") == "rbd1/testvolume"

    assert auth_el.get("username") == "libvirt"
    assert auth_secret_el.get("type") == "ceph"
    assert auth_secret_el.get("uuid") == "89890794-6310-4e93-81a1-0d37d601ab78"

    assert {h.get("name") for h in source_host_els} == {"mon1", "mon2", "mon3"}


def test_domain_add_bridge_interface():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
    )

    d.add_bridge_interface("br0", model_type="virtio")

    domain_el = ET.fromstring(str(d))

    interface_el = domain_el.find("./devices/interface")

    assert interface_el is not None
    assert interface_el.get("type") == "bridge"

    assert interface_el.find("./source").get("bridge") == "br0"
    assert interface_el.find("./model").get("type") == "virtio"

    assert interface_el.find("./mac") is None
    assert interface_el.find("./boot") is None


def test_domain_add_bridge_interface_mac_address():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
    )

    d.add_bridge_interface("br0", mac_address="00:de:ad:be:ef:00")

    domain_el = ET.fromstring(str(d))

    interface_el = domain_el.find("./devices/interface")

    assert interface_el.find("./mac").get("address") == "00:de:ad:be:ef:00"


def test_domain_add_bridge_interface_boot_order():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
    )

    d.add_bridge_interface("br0", boot_order=1)

    domain_el = ET.fromstring(str(d))

    interface_el = domain_el.find("./devices/interface")

    assert interface_el.find("./boot").get("order") == "1"


def test_domain_add_network_interface():
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=virConnect(),
        basexml=domainxml,
    )

    d.add_network_interface("mynetwork")

    domain_el = ET.fromstring(str(d))

    interface_el = domain_el.find("./devices/interface")

    assert interface_el is not None
    assert interface_el.get("type") == "network"

    assert interface_el.find("./source").get("network") == "mynetwork"
