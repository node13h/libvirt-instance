import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from libvirt_instance import domain


@pytest.fixture
def libvirt_conn_dir():
    conn = MagicMock()
    conn.storagePoolLookupByName = mock_storagePoolLookupByName
    conn.getCapabilities.return_value = """
<capabilities>
  <host>
    <cpu>
      <arch>x86_64</arch>
    </cpu>
  </host>
  <guest>
    <os_type>hvm</os_type>
    <arch name='x86_64'>
      <wordsize>64</wordsize>
      <emulator>/usr/bin/qemu-system-x86_64</emulator>
      <machine maxCpus='255'>pc-i440fx-6.2</machine>
      <machine canonical='pc-i440fx-6.2' maxCpus='255'>pc</machine>
      <domain type='qemu'>
        <emulator>/usr/bin/qemu</emulator>
        <machine maxCpus='255'>pc-i440fx-6.1</machine>
      </domain>
      <domain type='kvm'>
        <emulator>/usr/bin/qemu-kvm</emulator>
        <machine maxCpus='255'>pc-i440fx-7.0</machine>
      </domain>
    </arch>
    <features>
      <acpi default='on' toggle='yes'/>
      <apic default='on' toggle='no'/>
      <cpuselection/>
      <deviceboot/>
      <disksnapshot default='on' toggle='no'/>
    </features>
  </guest>

</capabilities>
    """

    return conn


def mock_storageVolLookupByName(vol_name):
    vol = MagicMock()
    vol.name.return_value = vol_name
    vol.XMLDesc.return_value = f"""
<volume type='file'>
  <name>{vol_name}</name>
  <key>/var/lib/libvirt/images/{vol_name}.img</key>
  <capacity unit='bytes'>554389504</capacity>
  <allocation unit='bytes'>554389504</allocation>
  <physical unit='bytes'>554389504</physical>
  <target>
    <path>/var/lib/libvirt/images/{vol_name}.img</path>
    <format type='raw'/>
    <permissions>
      <mode>0644</mode>
      <owner>0</owner>
      <group>0</group>
      <label>unconfined_u:object_r:unlabeled_t:s0</label>
    </permissions>
    <timestamps>
      <atime>1667514688.552875991</atime>
      <mtime>1654761281.264082627</mtime>
      <ctime>1654761281.264082627</ctime>
      <btime>0</btime>
    </timestamps>
  </target>
</volume>
 """

    return vol


def mock_pool_createXML(xml):
    pool = ET.fromstring(xml)

    vol_name = pool.find("./name").text

    return mock_storageVolLookupByName(vol_name)


def mock_storagePoolLookupByName(pool_name):
    pool = MagicMock()
    pool.XMLDesc.return_value = f"""
<pool type='dir'>
  <name>{pool_name}</name>
  <uuid>398b704a-9128-4c0d-9156-d97578ed19ec</uuid>
  <capacity unit='bytes'>17152606208</capacity>
  <allocation unit='bytes'>7409659904</allocation>
  <available unit='bytes'>9742946304</available>
  <source>
  </source>
  <target>
    <path>/var/lib/libvirt/images</path>
    <permissions>
      <mode>0755</mode>
      <owner>0</owner>
      <group>0</group>
      <label>system_u:object_r:unlabeled_t:s0</label>
    </permissions>
  </target>
</pool>
"""
    pool.listVolumes.return_value = ["testvolume2", "testvolume3"]

    pool.storageVolLookupByName = mock_storageVolLookupByName
    pool.name.return_value = pool_name
    pool.createXML = mock_pool_createXML

    return pool


def test_volume(libvirt_conn_dir):
    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    assert v.volume.name() == "testvolume"


def test_volume_existing(libvirt_conn_dir):
    with pytest.raises(domain.VolumeAlreadyExistsError):
        domain.Volume(
            "testvolume2",
            create_size_bytes=16777216,
            libvirt_conn=libvirt_conn_dir,
            pool_name="testpool",
        )


def test_volume_existing_ok(libvirt_conn_dir):
    v = domain.Volume(
        "testvolume2",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
        exist_ok=True,
    )

    assert v.volume.name() == "testvolume2"


def test_domain_init(libvirt_conn_dir):
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
        libvirt_conn=libvirt_conn_dir,
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


def test_domain_define(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
    )

    d.define()

    libvirt_conn_dir.defineXML.assert_called()


def test_domain_init_host_arch(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
        domain_type="kvm",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))
    os_type_el = domain_el.find("./os/type")

    assert os_type_el.get("arch") == "x86_64"


def test_domain_init_domain_type_specific_machine(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc-i440fx-7.0",
    )

    domain_el = ET.fromstring(str(d))
    os_type_el = domain_el.find("./os/type")

    assert os_type_el.get("arch") == "x86_64"


def test_domain_init_domain_type_specific_machine_wrong_domain_type(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=libvirt_conn_dir,
            basexml=domainxml,
            domain_type="kvm",
            arch_name="x86_64",
            machine="pc-i440fx-6.1",
        )


def test_domain_init_custom_domain_type(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
        domain_type="qemu",
        arch_name="x86_64",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))

    assert domain_el.get("type") == "qemu"


def test_domain_init_unsupported_domain_type(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=libvirt_conn_dir,
            basexml=domainxml,
            domain_type="UNSUPPORTED",
            arch_name="x86_64",
            machine="pc",
        )


def test_domain_init_custom_cpu(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
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


def test_domain_init_existing_cpu(libvirt_conn_dir):
    domainxml = "<domain><cpu><model>TestCPU</model></cpu></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
    )

    domain_el = ET.fromstring(str(d))
    cpu_model_el = domain_el.find("./cpu/model")

    assert cpu_model_el.text == "TestCPU"


def test_domain_init_existing_cpu_override(libvirt_conn_dir):
    domainxml = "<domain><cpu><model>TestCPU</model></cpu></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
        domain_type="kvm",
        arch_name="x86_64",
        machine="pc",
        cpu_model="SandyBridge",
    )

    domain_el = ET.fromstring(str(d))
    cpu_model_el = domain_el.find("./cpu/model")

    assert cpu_model_el.text == "SandyBridge"


def test_domain_init_unsupported_arch(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=libvirt_conn_dir,
            basexml=domainxml,
            domain_type="kvm",
            arch_name="INVALID",
            machine="pc",
        )


def test_domain_init_unsupported_machine(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    with pytest.raises(RuntimeError):
        domain.DomainDefinition(
            "foo",
            ram_bytes=16777216,
            vcpus=1,
            libvirt_conn=libvirt_conn_dir,
            basexml=domainxml,
            domain_type="kvm",
            arch_name="x86_64",
            machine="INVALID",
        )


def test_domain_add_disk_virtio_blk(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    d.add_disk(v, bus="virtio", cache="none")

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    assert disk_el.find("./boot") is None

    assert disk_el.find("./target").get("dev") == "vda"
    assert disk_el.find("./target").get("bus") == "virtio"

    assert disk_el.find("./source").get("pool") == "testpool"
    assert disk_el.find("./source").get("volume") == "testvolume"

    assert disk_el.find("./driver").get("cache") == "none"


def test_domain_add_disk_virtio_scsi(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    d.add_disk(v, bus="scsi", cache="none")

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    target_el = disk_el.find("./target")
    assert target_el.get("dev") == "sda"
    assert target_el.get("bus") == "scsi"

    source_el = disk_el.find("./source")
    assert source_el.get("pool") == "testpool"
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


def test_domain_add_disk_virtio_scsi_existing_controller(libvirt_conn_dir):
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

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
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


def test_domain_add_disk_multiple(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v1 = domain.Volume(
        "v1",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    v2 = domain.Volume(
        "v2",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    v3 = domain.Volume(
        "v3",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
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


def test_domain_add_disk_multiple_scsi(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v1 = domain.Volume(
        "v1",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    v2 = domain.Volume(
        "v2",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
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


def test_domain_add_disk_discard(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    d.add_disk(v, discard="unmap")

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    assert disk_el.find("./driver").get("discard") == "unmap"


def test_domain_add_disk_boot_order(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    d.add_disk(v, boot_order=1)

    domain_el = ET.fromstring(str(d))

    disk_el = domain_el.find("./devices/disk")

    assert disk_el is not None

    assert disk_el.find("./boot").get("order") == "1"


def test_domain_add_disk_unsupported_bus(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    v = domain.Volume(
        "testvolume",
        create_size_bytes=16777216,
        libvirt_conn=libvirt_conn_dir,
        pool_name="testpool",
    )

    with pytest.raises(domain.UnsupportedBusError):
        d.add_disk(v, bus="UNSUPPORTED BUS")


def test_domain_add_bridge_interface(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
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


def test_domain_add_bridge_interface_mac_address(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    d.add_bridge_interface("br0", mac_address="00:de:ad:be:ef:00")

    domain_el = ET.fromstring(str(d))

    interface_el = domain_el.find("./devices/interface")

    assert interface_el.find("./mac").get("address") == "00:de:ad:be:ef:00"


def test_domain_add_bridge_interface_boot_order(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    d.add_bridge_interface("br0", boot_order=1)

    domain_el = ET.fromstring(str(d))

    interface_el = domain_el.find("./devices/interface")

    assert interface_el.find("./boot").get("order") == "1"


def test_domain_add_network_interface(libvirt_conn_dir):
    domainxml = "<domain></domain>"

    d = domain.DomainDefinition(
        "foo",
        ram_bytes=16777216,
        vcpus=1,
        libvirt_conn=libvirt_conn_dir,
        basexml=domainxml,
    )

    d.add_network_interface("mynetwork")

    domain_el = ET.fromstring(str(d))

    interface_el = domain_el.find("./devices/interface")

    assert interface_el is not None
    assert interface_el.get("type") == "network"

    assert interface_el.find("./source").get("network") == "mynetwork"
