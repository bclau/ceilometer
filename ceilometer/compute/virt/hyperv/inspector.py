# -*- encoding: utf-8 -*-
#
# Copyright © 2012 Red Hat, Inc
#
# Author: Eoghan Glynn <eglynn@redhat.com>
#         Doug Hellmann <doug.hellmann@dreamhost.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
# @author: Claudiu Belu, Cloudbase Solutions Srl
"""Implementation of Inspector abstraction for Hyper-V"""

import collections

from oslo.config import cfg
from stevedore import driver

from ceilometer.compute.virt import inspector as virt_inspector
from ceilometer.compute.virt.hyperv import utilsv2
from ceilometer.openstack.common import log


hyperv_opts = [

]

CONF = cfg.CONF
CONF.register_opts(hyperv_opts)

LOG = log.getLogger(__name__)


# Main virt inspector abstraction layering over the hypervisor API.
#
class HypervInspector(virt_inspector.Inspector):

    def __init__(self):
        self._utils = utilsv2.UtilsV2()

    def inspect_instances(self):
        for element_name, name in self._utils.get_all_instances():
            yield virt_inspector.Instance(
                name=element_name,
                UUID=name)

    def inspect_cpus(self, instance_name):
        cpu_count, cpu_time = self._utils.get_cpu_info(instance_name)
        return virt_inspector.CPUStats(number=cpu_count, time=cpu_time)

    def inspect_vnics(self, instance_name):
        vm = self._utils.lookup_vm(instance_name)
        for vm_nic_port in self._utils.get_vm_nic_ports(instance_name):
            vm_nic = self._utils.get_vm_nic_for_port(vm, vm_nic_port)
            nic_stats = self._utils.get_port_info(vm_nic_port)

            interface = virt_inspector.Interface(
                name=vm_nic.ElementName,
                mac=vm_nic.Address,
                fref=None,
                parameters=None)

            stats = virt_inspector.InterfaceStats(
                rx_bytes=nic_stats['rx_bytes'],
                rx_packets=0,
                tx_bytes=nic_stats['tx_bytes'],
                tx_packets=0)

            yield (interface, stats)

    def inspect_disks(self, instance_name):
        for vm_disk in self._utils.get_disks(instance_name):
            disk_stats = self._utils.get_disk_info(vm_disk)

            disk = virt_inspector.Disk(device=vm_disk)
            stats = virt_inspector.DiskStats(
                read_requests=0,
                read_bytes=disk_stats['read_bytes'],
                write_requests=0,
                write_bytes=disk_stats['write_bytes'],
                errors=0)

            yield (disk, stats)
