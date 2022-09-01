# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Copyright (C) 2019 Linaro Limited
# Author: Dan Rue <dan.rue@linaro.org>
#
# Copyright (C) 2019, 2021-2023 Collabora Limited
# Author: Guillaume Tucker <guillaume.tucker@collabora.com>
# Author: Michal Galka <michal.galka@collabora.com>

from jinja2 import Environment, FileSystemLoader
import os
import re
from kernelci.runtime import add_kci_raise, Runtime

CROS_CONFIG_RE = re.compile(r'cros://chromeos-([0-9.]+)/([a-z0-9_]+)/([a-z0-9-._]+).flavour.config(\+[a-z0-9-+]+)?')  # noqa

CROS_FLAVOURS = {
    'chromeos-amd-stoneyridge': 'ston',
    'chromeos-intel-denverton': 'denv',
    'chromeos-intel-pineview': 'pine',
    'chromiumos-arm': 'arm',
    'chromiumos-arm64': 'arm64',
    'chromiumos-mediatek': 'mtk',
    'chromiumos-qualcomm': 'qcom',
    'chromiumos-rockchip': 'rk32',
    'chromiumos-rockchip64': 'rk64',
    'chromiumos-x86_64': 'x86',
}

CROS_DEVICE_TYPES = {
    'hp-x360-12b-ca0500na-n4000-octopus_chromeos': 'octopus-n4000',
    'hp-x360-12b-ca0010nr-n4020-octopus_chromeos': 'octopus-n4020',
    'qemu_x86_64-uefi-chromeos': 'qemu-x86',
}


class LavaRuntime(Runtime):
    DEFAULT_TEMPLATE_PATHS = ['config/lava', '/etc/kernelci/lava']

    def generate(self, params, device_config, plan_config, callback_opts=None,
                 templates_paths=None):
        if templates_paths is None:
            templates_paths = self.DEFAULT_TEMPLATE_PATHS
        short_template_file = plan_config.get_template_path(
            device_config.boot_method)
        base_name = params['base_device_type']
        priority = self._get_priority(plan_config)
        params.update({
            'queue_timeout': self.config.queue_timeout,
            'lab_name': self.config.name,
            'base_device_type': self._alias_device_type(base_name),
            'priority': priority,
            'name': self._shorten_cros_name(params),
        })
        if callback_opts:
            self._add_callback_params(params, callback_opts)
        jinja2_env = Environment(loader=FileSystemLoader(templates_paths),
                                 extensions=["jinja2.ext.do"])
        add_kci_raise(jinja2_env)
        template = jinja2_env.get_template(short_template_file)
        data = template.render(params)
        return data

    def submit(self, job_path):
        with open(job_path, 'r') as job_file:
            job = job_file.read()
            job_id = self._submit(job)
            return job_id

    def _shorten_cros_defconfig(self, defconfig):
        kver, arch, flav, frag = CROS_CONFIG_RE.match(defconfig).groups()
        frag = frag.strip('+').replace('+', '-') if frag else ''
        flav = CROS_FLAVOURS.get(flav) or flav
        return '-'.join((arch, flav, kver, frag))

    def _shorten_cros_device_type(self, device_type):
        return CROS_DEVICE_TYPES.get(device_type) or device_type

    def _shorten_cros_name(self, params):
        defconfig_full = params['defconfig_full']
        if defconfig_full.startswith('cros:'):
            return '-'.join((
                params['tree'],
                params['git_branch'],
                params['git_describe'],
                params['arch'],
                self._shorten_cros_defconfig(defconfig_full),
                params['build_environment'],
                self._shorten_cros_device_type(params['device_type']),
                params['plan'],
            )).replace('/', '-')
        else:
            return params['name']

    def job_file_name(self, params):
        return '.'.join([params['name'], 'yaml'])

    def _get_priority(self, plan_config):
        # Scale the job priority (from 0-100) within the available levels
        # for the lab, or use the lowest by default.
        priority = plan_config.params.get('priority', 20)
        if self.config.priority:
            priority = int(priority * self.config.priority / 100)
        elif (self.config.priority_max is not None and
              self.config.priority_min is not None):
            prio_range = self.config.priority_max - self.config.priority_min
            prio_min = self.config.priority_min
            priority = int((priority * prio_range / 100) + prio_min)
        return priority

    def _add_callback_params(self, params, opts):
        callback_id = opts.get('id')
        if not callback_id:
            return
        callback_type = opts.get('type')
        if callback_type == 'kernelci':
            lava_cb = 'boot' if params['plan'] == 'boot' else 'test'
            # ToDo: consolidate this to just have to pass the callback_url
            params['callback_name'] = '/'.join(['lava', lava_cb])
        params.update({
            'callback': callback_id,
            'callback_url': opts['url'],
            'callback_dataset': opts['dataset'],
            'callback_type': callback_type,
        })
