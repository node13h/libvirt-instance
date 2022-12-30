# libvirt-instance

`libvirt-instance` is a CLI tool for creating virtual machines. It uses the
Libvirt API, and is compatible with other Libvirt applications.

Think of it as a more opinionated alternative to `virt-install`.


## Project goals

- Make creating Libvirt virtual machines (VMs) via the command-line interface
  simpler for human operators, by providing a way to group some commonly-used
  configurations as presets.
- Provide a convenient way to deploy cloud instances on Libvirt without the
  need for a metadata service (the
  [NoCloud](https://cloudinit.readthedocs.io/en/latest/topics/datasources/nocloud.html)
  data source is used to provide metadata to instances).

The tool does not support deleting Libvirt resources, and there are no plans to
implement that so far. Any delete operations can be performed using `virsh`.


## Installation

This package depends on `libvirt-python`. Installing into a virtualenv might
require GCC, Python3 and Libvirt development OS packages to be installed.
Run `dnf --enablerepo=devel install gcc python3-devel libvirt-devel` to install
those packages if you're using RockyLinux 9.

Otherwise (when not using virtualenv), having the `python3-libvirt` OS package
installed should be sufficient.

`libvirt-instance` can be installed by running `pip3 install libvirt-instance`.
It requires Python 3.9+ to run.


## Showcase

While both local and remote Libvirt daemons are supported, the following example
is using a local Libvirt daemon for sake of simplicity. The commands should be
executed by a user who has sufficient Libvirt access privileges.

```shell
URI=qemu:///system

# All operations on disks are done using the Libvirt pool APIs.
# Libvirt doesn't usually come with any storage pools defined, so let's define
# one named "images".
virsh -c "$URI" pool-define-as images dir --target /var/lib/libvirt/images
virsh -c "$URI" pool-autostart images
virsh -c "$URI" pool-start images

# Create a config file with a preset for disks from the above pool,
# and a preset for network interfaces in the default Libvirt NAT network (this
# network exists by default).
cat <<"EOF" >./libvirt-instance-config.yaml
preset:
  disk:
    local:
      type: volume
      pool: images
      bus: virtio
      cache: none
  interface:
    nat:
      type: network
      model-type: virtio
      network: default
EOF

# Fetch a cloud image from the Internet and upload it to Libvirt as a volume,
# so we can use it as the base image for VM disks.
curl -LfsS \
  https://download.fedoraproject.org/pub/fedora/linux/releases/37/Cloud/x86_64/images/Fedora-Cloud-Base-37-1.7.x86_64.raw.xz \
  | xzcat >./f37-cloud-amd64.raw
image_size=$(stat --printf="%s" ./f37-cloud-amd64.raw)
virsh -c "$URI" vol-create-as images f37-cloud-amd64.raw "${image_size}b" --format raw
virsh -c "$URI" vol-upload f37-cloud-amd64.raw ./f37-cloud-amd64.raw --pool images

# Generate a passphraseless SSH key for this demo.
ssh-keygen -f mykey -N ''

# Create user-data.
cat <<EOF >./user-data
#cloud-config
ssh_authorized_keys:
  - $(cat ./mykey.pub)
packages:
  - nginx
runcmd:
  - systemctl start nginx
EOF

# Create network-config.
cat <<"EOF" >./network-config
version: 2
ethernets:
    eth0:
        dhcp4: false
        dhcp6: false
        addresses:
          - 192.168.122.10/24
        gateway4: 192.168.122.1
        nameservers:
          addresses:
            - 1.1.1.1
            - 8.8.8.8
EOF

# Create the VM.
# headless-server-x86_64 is a built-in domain preset.
instance_id=$(
  libvirt-instance -c "$URI" --config-file ./libvirt-instance-config.yaml create \
                   --domain-preset headless-server-x86_64 \
                   --memory 2GiB \
                   --vcpu 2 \
                   --disk local,5GiB,source=f37-cloud-amd64.raw \
                   --nic nat \
                   --cloud-seed-disk=local \
                   --cloud-user-data-file ./user-data \
                   --cloud-network-config-file ./network-config \
                   myvm \
    | jq -er '."instance-id"')

# Start the VM.
virsh -c "$URI" start "$instance_id"

# Wait until cloud-init has finished executing.
until
  ssh -i mykey \
      -o IdentitiesOnly=true \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      fedora@192.168.122.10 \
      cloud-init status --wait
do
  sleep 1
done

# Get a page from Nginx on the VM.
curl http://192.168.122.10/

# Cleanup.
virsh -c "$URI" destroy "$instance_id"
virsh -c "$URI" undefine "$instance_id" --nvram --remove-all-storage
```


## More examples

Creating non-image-based VMs is also an option.

This example creates a VM with two disks and the PXE boot as the first option:

```shell
libvirt-instance -c "$URI" --config-file ./libvirt-instance-config.yaml create \
                 --domain-preset headless-server-x86_64 \
                 --memory 2GiB \
                 --vcpu 2 \
                 --disk local,5GiB,boot-order=2 \
                 --disk local,10GiB \
                 --nic nat,boot-order=1 \
                 myvm
```

Alternative/non-native architectures are also supported. `libvirt-instance` comes
with two built-in domain presets - `headless-server-x86_64` and
`headless-server-aarch64`. More presets can be defined in a config file.

Run `libvirt-instance get-config` to see the currently-defined presets.

The following example deploys an ARM cloud image-based Fedora VM on a non-ARM KVM host:

```shell
curl -LfsS \
  https://download.fedoraproject.org/pub/fedora/linux/releases/37/Cloud/aarch64/images/Fedora-Cloud-Base-37-1.7.aarch64.raw.xz \
  | xzcat >./f37-cloud-arm64.raw
image_size=$(stat --printf="%s" ./f37-cloud-arm64.raw)
virsh -c "$URI" vol-create-as images f37-cloud-arm64.raw "${image_size}b" --format raw
virsh -c "$URI" vol-upload f37-cloud-arm64.raw ./f37-cloud-arm64.raw --pool images

libvirt-instance -c "$URI" --config-file ./libvirt-instance-config.yaml create \
                 --domain-preset headless-server-aarch64 \
                 --cpu-model cortex-a57 \
                 --domain-type qemu \
                 --memory 2GiB \
                 --vcpu 2 \
                 --disk local,5GiB,source=f37-cloud-arm64.raw \
                 --nic nat \
                 --cloud-seed-disk=local \
                 --cloud-user-data-file ./user-data \
                 --cloud-network-config-file ./network-config \
                 myvm
```


## Configuration file

Some defaults and presets are already built in. Configuration file is a way to
add more presets, or override existing presets and settings.

Three types of presets are currently supported: `domain`, `disk`, and `interface`.

The default location of the config file is `/etc/libvirt-instance-config.yaml`.
The `--config-file` CLI argument provides a way to override that.

Run `libvirt-instance get-config` to see the current config.


### Domain presets

Example config snippet:

```yaml
preset:
  domain:
    windows-server:
      arch-name: x86_64
      machine-type: pc
      xml-file: /path/to/windows-server-base.xml
```

The above preset can be selected on the CLI using `--domain-preset windows-server`
when creating a new VM.

`arch-name` can be any arhitecture (e.g. `x86_64`, `aarch64`) supported by the
target host.

`machine-type` can be any machine type (e.g. `pc`, `q35`, `virt`) supported by
the chosen architecture.

`xml-file` specifies a file containing some
[domain XML](https://libvirt.org/formatdomain.html) used as the foundation for
the VM being created. The tool will fill in the architecture, domain and
machine type, CPU (count and model), memory size, network interface,
disk (including any necessary SCSI controllers) entries into the base XML
automatically using the information from presets and CLI arguments.

Domain XML may alternatively be provided inline via the `xml` key.


### Disk presets

All operations on disks are done using Libvirt pool APIs, so disk presets may
only reference Libvirt pools.

Currently `dir`, `logical`, and `rbd` pools are supported.

Example config snippet:

```yaml
preset:
  disk:
    ceph-ssd:
      type: volume
      pool: ceph-rbd-ssd
      bus: scsi
      cache: writeback
    ceph-hdd:
      type: volume
      pool: ceph-rbd
      bus: virtio
      cache: writeback
    x86worker:
      type: volume
      pool: local-lvm1
      bus: virtio
      cache: none
      source: fedora37-cloud-amd64.raw
      source-pool: ceph-rbd

```
CLI examples for the above: `--disk ceph-ssd,16GiB --disk ceph-hdd,1TiB`,
`--disk x86worker,32GiB`.

The only supported value for `type` is `volume` at the moment.

`pool` specifies a target Libvirt pool for the volumes. This pool will also be
used to pull any information about volumes when adding disk devices to the
domain XML.

`bus` is either `virtio` for virtio-blk disks, or `scsi` for virtio-scsi disks.

`cache` specifies any disk cache mode supported by Libvirt.

`source` specifies a Libvirt volume containing the base image for disks.

`source-pool` specifies the Libvirt pool for the `source` image. Defaults to the
same value as `pool` when not specified.

`boot-order` sets the device position in the boot order.

In most cases, the resulting disk device description in the domain XML will be a
volume reference (`<disk type="volume">`). Some pool types (`rbd` for instance)
do not support backing volume disks yet
(see [domain_conf.c#L29929-L29939](https://github.com/libvirt/libvirt/blob/v8.10.0/src/conf/domain_conf.c#L29929-L29939).
When adding disks from such pools, `libvirt-instance` will transparently inline
the disk definition into the domain XML using the information (MONs, auth)
from the pool.


### Interface presets

Currently `bridge` and `network` type interfaces are supported.

Example config snippet:

```yaml
preset:
  interface:
    nat:
      type: network
      model-type: virtio
      network: default
    dmz:
      type: bridge
      model-type: virtio
      bridge: br0
    storage:
      type: bridge
      model-type: virtio
      bridge: br1
      mtu: 9000
```

CLI examples for the above: `--nic nat`, `--nic dmz --nic storage`.

`model-type` specifies any model type supported by Libvirt (e.g. `virtio`,
`e1000`, `rtl8139`, etc).

`network` specifies the Libvirt network name for `type: network` interfaces.

`bridge` specifies the name of an existing network bridge for `type: bridge`
interfaces.

`mtu` sets the MTU on the host-side TAP interface. Note, the MTU also needs
to be configured inside the guest.

`boot-order` sets the device position in the boot order.

Technically, `mac-address` can also be specified in an interface preset, but
it makes more sense to specify any MAC addresses on the command line
(e.g. `--nic nat,mac-address=00:11:22:33:44:55:66`).


## CLI options

See `libvirt-instance --help` for the full list of CLI options.
There are also some examples in the "Showcase" and "More examples" sections
illustrating how different options work together.

`--disk <SPEC>` may be specified more than once to attach multiple disks to a
VM. Disks are created using the `<VM-NAME>-disk<N>` naming scheme. If a volume
with the same name already exists in the target pool - `libvirt-instance` will
exit with an error.
Disks are attached to the instance in the same order as specified on the command
line.

The `pool`, `bus`, `cache`, `source`, `source-pool`, and `boot-order` options
may be included in the disk spec, taking precedence over any corresponding
options from the chosen preset.
For example:
`--disk local,10GiB,bus=scsi,cache=writeback,source=jammy-server-cloudimg-amd64.img`.

`--nic <SPEC>` may also be specified more than once. The `mac-address`,
`model-type`, `network`, `bridge`, `mtu`, and `boot-order` options are supported
by `--nic`, similar to `--disk` options.

`--cloud-seed-disk` enables the cloud-init support and is required when
either `--cloud-user-data-file` or `--cloud-network-config-file` have been
specified.
It works like `--disk` without the size part. `--cloud-seed-disk` specifies
which disk preset to use when creating the
[NoCloud](https://cloudinit.readthedocs.io/en/latest/topics/datasources/nocloud.html)
seed disk.
The naming pattern for the seed disk is `<VM-NAME>-seed`.
Example: `--cloud-seed-disk local,bus=scsi`.


## Developing

See [DEVELOPING.md](DEVELOPING.md)
