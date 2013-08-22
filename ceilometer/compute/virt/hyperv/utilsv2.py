# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Cloudbase Solutions Srl
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
# @author: Claudiu Belu, Cloudbase Solutions Srl
"""
Utility class for VM related operations.
Based on the "root/virtualization/v2" namespace available starting with
Hyper-V Server / Windows Server 2012.
"""

import sys
import uuid

if sys.platform == 'win32':
    import wmi

from oslo.config import cfg

from ceilometer.compute.virt import inspector
from ceilometer.openstack.common import log as logging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class UtilsV2(object):

    _VIRTUAL_SYSTEM_TYPE_REALIZED = 'Microsoft:Hyper-V:System:Realized'

    _PROC_SETTING = 'Msvm_ProcessorSettingData'
    _SYNTH_ETH_PORT = 'Msvm_SyntheticEthernetPortSettingData'
    _ETH_PORT_ALLOC = 'Msvm_EthernetPortAllocationSettingData'
    _STORAGE_ALLOC = 'Msvm_StorageAllocationSettingData'

    _AGGREG_METRIC = 'Msvm_AggregationMetricDefinition'
    _METRICS_ME = 'Msvm_MetricForME'

    _CPU_METRIC_NAME = 'Aggregated Average CPU Utilization'
    _NET_IN_METRIC_NAME = 'Aggregated Filtered Incoming Network Traffic'
    _NET_OUT_METRIC_NAME = 'Aggregated Filtered Outgoing Network Traffic'
    _DISK_RD_METRIC_NAME = 'Aggregated Disk Data Read'
    _DISK_WR_METRIC_NAME = 'Aggregated Disk Data Writtem'

    def __init__(self, host='.'):
        self._init_hyperv_wmi_conn(host)
        self._init_cimv2_conn(host)
        self._init_cpu_speed()
        self._enable_metrics_for_host()

    def _init_hyperv_wmi_conn(self, host):
        self._conn = wmi.WMI(moniker='//%s/root/virtualization/v2' % host)

    def _init_cimv2_conn(self, host):
        self._cimv2 = wmi.WMI(moniker='//%s/root/cimv2' % host)

    def _init_cpu_speed(self):
        host_cpus = self._cimv2.Win32_Processor()
        self._host_cpu_speed = len(host_cpus) * host_cpus[0].MaxClockSpeed

    def _enable_metrics_for_host(self):
        self._enable_metric_def(self._CPU_METRIC_NAME)
        self._enable_metric_def(self._NET_IN_METRIC_NAME)
        self._enable_metric_def(self._NET_OUT_METRIC_NAME)

        for vm_name, name in self.get_all_instances():
            self._control_metrics(self.lookup_vm(vm_name).path_(), None)

    def get_all_instances(self):
        vms = [[v.ElementName, v.Name] for v in
               self._conn.Msvm_ComputerSystem(['ElementName', 'Name'],
                                              Caption="Virtual Machine")]
        return vms

    def get_cpu_info(self, instance_name):

        instance = self.lookup_vm(instance_name)
        cpu_sd = self._get_resources_vm(instance, self._PROC_SETTING)[0]
        cpu_metrics_def = self._get_metric_def(self._CPU_METRIC_NAME)

        cpu_metric_aggr = self._find_metrics(instance, cpu_metrics_def)[0]
        cpu_used = float(cpu_metric_aggr.MetricValue)
        cpu_percent = cpu_used / self._host_cpu_speed
        cpu_time = int(instance.OnTimeInMilliseconds) * cpu_percent
        cpu_count = cpu_sd.VirtualQuantity

        print cpu_used, cpu_percent, cpu_time
        return cpu_count, cpu_time

    def get_vm_nic_ports(self, instance_name):
        ports = self._get_resources(instance_name, self._ETH_PORT_ALLOC)
        return ports

    def get_vm_nic_for_port(self, vm, port):
        nics = self._get_resources_vm(vm, self._SYNTH_ETH_PORT)
        return [v for v in nics if port.Parent == v.path_()][0]

    def get_port_info(self, port):
        all_metrics = port.associators(wmi_association_class=self._METRICS_ME)
        wanted_metrics = {}
        for metr_name in [self._NET_IN_METRIC_NAME, self._NET_OUT_METRIC_NAME]:
            net_metric_def = self._get_metric_def(metr_name)
            net_metrics = self._filter_metrics(all_metrics, net_metric_def)
            metric_val = 0
            for net_metric in net_metrics:
                metric_val += int(net_metric.MetricValue)
            wanted_metrics[metr_name] = metric_val
            #print metric_val, net_metric_def

        return {
            'rx_bytes': wanted_metrics[self._NET_IN_METRIC_NAME],
            'tx_bytes': wanted_metrics[self._NET_OUT_METRIC_NAME]
        }

    def get_disks(self, instance_name):
        disks = self._get_resources(instance_name, self._STORAGE_ALLOC)
        return disks

    def get_disk_info(self, disk):
        all_metrics = disk.associators(wmi_association_class=self._METRICS_ME)
        wanted_metrics = {}
        for mtr_name in [self._DISK_RD_METRIC_NAME, self._DISK_WR_METRIC_NAME]:
            disk_metric_def = self._get_metric_def(mtr_name)
            if not disk_metric_def:
                wanted_metrics[mtr_name] = 0
                continue

            disk_metric = self._filter_metrics(all_metrics, disk_metric_def)[0]
            wanted_metrics[metr_name] = int(disk_metric.MetricValue)
            #print disk_metric, disk_metric_def

        return {
            'read_bytes': wanted_metrics[self._DISK_RD_METRIC_NAME],
            'write_bytes': wanted_metrics[self._DISK_WR_METRIC_NAME]
        }

    def lookup_vm(self, vm_name):
        vms = self._conn.Msvm_ComputerSystem(ElementName=vm_name)
        n = len(vms)
        if n == 0:
            msg = 'VM %(vm_name)s not found on Hyper-V.'
            raise inspector.InstanceNotFoundException(msg)
        elif n > 1:
            raise Exception('Duplicate VM name found: %(vm_name)s')
        else:
            return vms[0]

    def _find_metrics(self, vm, metric_def):
        return self._filter_metrics(
            vm.associators(wmi_association_class=self._METRICS_ME), metric_def)

    def _filter_metrics(self, all_metrics, metric_def):
        return [v for v in all_metrics if
                v.MetricDefinitionId == metric_def.Id]

    def _get_metric_def(self, metric_def):
        metric = self._conn.CIM_BaseMetricDefinition(ElementName=metric_def)
        if metric:
            return metric[0]

    def _enable_metric_def(self, metric_def):
        self._control_metrics(None, self._get_metric_def(metric_def).path_())

    def _control_metrics(self, subject, definition):
        metrics_svc = self._conn.Msvm_MetricService()[0]
        metrics_svc.ControlMetrics(
            Subject=subject,
            Definition=definition,
            MetricCollectionEnabled=2)

    def _get_vm_setting_data(self, vm):
        vmsettings = vm.associators(
            wmi_result_class='Msvm_VirtualSystemSettingData')
        # Avoid snapshots
        return [s for s in vmsettings if
                s.VirtualSystemType == self._VIRTUAL_SYSTEM_TYPE_REALIZED][0]

    def _get_resources(self, vm_name, resource_class):
        vm = self.lookup_vm(vm_name)
        return self._get_resources_vm(vm, resource_class)

    def _get_resources_vm(self, vm, resource_class):
        setting_data = self._get_vm_setting_data(vm)
        return setting_data.associators(wmi_result_class=resource_class)
