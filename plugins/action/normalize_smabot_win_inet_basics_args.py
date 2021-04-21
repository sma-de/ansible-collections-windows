
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from urllib.parse import urlparse

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import NormalizerBase, DefaultSetterConstant
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.windows.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMergerWin



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ProxyNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


class ProxyNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'all_users', DefaultSetterConstant(True)
        )

        self._add_defaultsetter(kwargs, 
           'forward', DefaultSetterConstant(True)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ProxyConfigNormalizer(pluginref),
          ProxyAuthNormalizer(pluginref),
        ]

        super(ProxyNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['proxy']


class ProxyConfigNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(ProxyConfigNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['config']

    @property
    def simpleform_key(self):
        return 'proxy'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if not my_subcfg:
            ## no proxy set, dont do proxy
            return my_subcfg

        setdefault_none(my_subcfg, 'auto_detect', False)

        return my_subcfg


class ProxyAuthNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(ProxyAuthNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['auth']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if not my_subcfg:
            ## no authing set, dont do authing
            return my_subcfg

        my_subcfg.update({
          'type': 'generic_password',
          'state': 'present',
          'name': urlparse(cfg['proxy']['config']['proxy']).hostname,
        })

        return my_subcfg



class ActionModule(ConfigNormalizerBaseMergerWin):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self), 
            *args, default_merge_vars=['smabot_win_inet_basics_args_defaults'], 
            extra_merge_vars_ans=['extra_smabot_win_inet_basics_args_config_maps'], 
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_win_inet_basics_args'

    @property
    def allow_empty(self):
        return True

