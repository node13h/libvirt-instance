import copy
import xml.etree.ElementTree as ET

import libvirt  # type: ignore


class libvirtError(libvirt.libvirtError):
    def __init__(self, msg: str):

        Exception.__init__(self, msg)

        self.err = None


class virStorageVol(object):
    def __init__(self, *args, _xml, _pool, **kwargs):
        self._xml_el = ET.fromstring(_xml)

        target_el = ET.Element("target")
        target_path_el = ET.SubElement(target_el, "path")

        pool_type = _pool._xml_el.get("type")

        if pool_type in ("dir", "logical"):
            target_path_el.text = "/".join(
                [_pool._xml_el.find("./target/path").text, self.name()]
            )
        elif pool_type == "rbd":
            target_path_el.text = "/".join(
                [_pool._xml_el.find("./source/name").text, self.name()]
            )

        self._xml_el.append(target_el)

    def XMLDesc(self, flags=0):
        return ET.tostring(self._xml_el, encoding="unicode")

    def name(self):
        return self._xml_el.find("./name").text

    def info(self):
        capacity = int(self._xml_el.find("./capacity").text)
        allocation = int(self._xml_el.find("./allocation").text)
        available = capacity

        return capacity, allocation, available

    # TODO: Check current volume capacity, pool capacity, etc.
    def resize(self, capacity, flags=0):
        self._xml_el.find("./capacity").text = str(capacity)


class virStoragePool:
    def __init__(self, *args, _xml, **kwargs):
        self._volumes = {}
        self._xml_el = ET.fromstring(_xml)

    def XMLDesc(self, flags=0):
        return ET.tostring(self._xml_el, encoding="unicode")

    def listVolumes(self):
        return list(self._volumes.keys())

    def name(self):
        return self._xml_el.find("./name").text

    def createXML(self, xmlDesc, flags=0):
        volume = virStorageVol(_xml=xmlDesc, _pool=self)
        self._volumes[volume.name()] = volume

        return volume

    def createXMLFrom(self, xmlDesc, clonevol, flags=0):
        volume_el = copy.deepcopy(clonevol._xml_el)
        name = ET.fromstring(xmlDesc).find("./name").text

        if name in self._volumes:
            raise libvirtError(f"Volume {name} already exists.")

        volume_el.find("./name").text = name

        return self.createXML(ET.tostring(volume_el, encoding="unicode"))

    def storageVolLookupByName(self, name):
        try:
            return self._volumes[name]
        except KeyError:
            raise libvirtError(f"Volume {name} does not exist.")


class virDomain(object):
    def __init__(self, *args, _xml, **kwargs):
        self._xml = _xml

    def name(self):
        domain_el = ET.fromstring(self._xml)
        return domain_el.find("./name").text


class virConnect:
    def __init__(self, *args, **kwargs):
        self._domains = {}
        self._pools = {}

        default_pool_xml = """
<pool type='dir'>
  <name>default</name>
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
</pool>"""

        self._pools["default"] = virStoragePool(_xml=default_pool_xml)

        logical_pool_xml = """
<pool type='logical'>
  <name>scratch</name>
  <uuid>cfbf8539-b6e4-46cd-a389-fc0afc2dd089</uuid>
  <capacity unit='bytes'>500057505792</capacity>
  <allocation unit='bytes'>0</allocation>
  <available unit='bytes'>500057505792</available>
  <source>
    <name>scratch</name>
    <format type='lvm2'/>
  </source>
  <target>
    <path>/dev/scratch</path>
  </target>
</pool>"""

        self._pools["logical"] = virStoragePool(_xml=logical_pool_xml)

        ceph_pool_xml = """
<pool type='rbd'>
  <name>ceph</name>
  <uuid>20ad2b50-50a9-4423-8eaa-72b481947da9</uuid>
  <capacity unit='bytes'>101779903610880</capacity>
  <allocation unit='bytes'>12070043725569</allocation>
  <available unit='bytes'>65141153693696</available>
  <source>
    <host name='mon1'/>
    <host name='mon2'/>
    <host name='mon3'/>
    <name>rbd1</name>
    <auth type='ceph' username='libvirt'>
      <secret uuid='89890794-6310-4e93-81a1-0d37d601ab78'/>
    </auth>
  </source>
</pool>"""

        self._pools["ceph"] = virStoragePool(_xml=ceph_pool_xml)

        self._capabilities_xml = """
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

    def getCapabilities(self):
        return self._capabilities_xml

    def storagePoolLookupByName(self, name):
        try:
            return self._pools[name]
        except KeyError:
            raise libvirtError(f"Pool {name} does not exist.")

    def defineXML(self, xml):
        domain = virDomain(_xml=xml)
        self._domains[domain.name()] = domain

        return domain
