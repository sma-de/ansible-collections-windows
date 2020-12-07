
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import pathlib
import os

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBase, NormalizerBase, DefaultSetterConstant
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWin
from ansible_collections.smabot.windows.plugins.action import command_info



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          NssmInstallNormalizer(pluginref),
          ServiceNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)
 
 
class NssmInstallNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'name', DefaultSetterConstant('nssm')
        )

        self._add_defaultsetter(kwargs, 
           'state', DefaultSetterConstant('latest')
        )

        super(NssmInstallNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['nssm']


class ServiceNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ServiceCreateNormalizer(pluginref),
          ServiceConfigNormalizer(pluginref),
        ]

        super(ServiceNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['service']


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        setdefault_none(my_subcfg, 'user', 
           self.pluginref.get_become_settings()['become_user']
        )

        custom_pvar = my_subcfg.get('custom_pathvar', None)

        if custom_pvar:
            tmp = custom_pvar.get('prepend', [])

            if not custom_pvar.get('replace', False):
                # determine how default $PATH var looks like 
                # on target system for service user
                tmp += self.pluginref.exec_powershell_script(
                   '(Get-Childitem -LiteralPath env:path).Value', data_return=True
                )['result_json'].split(';')

            tmp += custom_pvar.get('append', [])

            custom_pvar['_export'] = ';'.join(tmp)

        return my_subcfg


class ServiceSubNormer(NormalizerBase):

    def _name_from_parent(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg.update(self.copy_from_parent(cfg, cfgpath_abs, ['name']))


class ServiceCreateNormalizer(ServiceSubNormer):

    def __init__(self, pluginref, *args, **kwargs):
        super(ServiceCreateNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )


    @property
    def config_path(self):
        return ['create']


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        self._name_from_parent(cfg, my_subcfg, cfgpath_abs)

        custom_pvar = self.get_parentcfg(
           cfg, cfgpath_abs
        ).get('custom_pathvar', {}).get('_export', None)

        if custom_pvar:
            appenv = setdefault_none(my_subcfg, 'app_environment', {})
            appenv['Path'] = custom_pvar

        return my_subcfg


class ServiceConfigNormalizer(ServiceSubNormer):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'state', DefaultSetterConstant('started')
        )

        self._add_defaultsetter(kwargs, 
           'start_mode', DefaultSetterConstant('auto')
        )

        super(ServiceConfigNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )


    @property
    def config_path(self):
        return ['config']


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        self._name_from_parent(cfg, my_subcfg, cfgpath_abs)
        my_subcfg['username'] = self.get_parentcfg(cfg, cfgpath_abs)['user']
        return my_subcfg


class ActionModule(ConfigNormalizerBase, ActionBaseWin):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            ConfigRootNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'winservice_nssm_args'

    @property
    def supports_merging(self):
        return False

