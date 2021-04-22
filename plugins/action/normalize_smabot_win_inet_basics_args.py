
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy
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
        ]

        super(ProxyNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['proxy']

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        proxy_cfg = my_subcfg['config']

        if not proxy_cfg:
            return my_subcfg

        # normalize protocol specific proxy servers
        proxy_settings = {}
        tmp = proxy_cfg['proxy'].split(';')

        bypass = proxy_cfg.get('bypass', None)

        global_sets = {}

        if bypass:
            global_sets['bypass_list'] = bypass
            global_sets['bypass_local'] = '<local>' in bypass

        for protproxy in tmp:
            protproxy = protproxy.split('=')

            assert len(protproxy) <= 2

            if len(protproxy) == 1:
                uri = protproxy[0]
                prots = None
            else:
                prots, uri = protproxy
                prots = [ prots ]

            assert prots or len(tmp) == 1, \
                "must specify protocol scheme when more than one proxy server is used"

            prots = prots or ['http', 'https', 'ftp', 'socks']

            for p in prots:
                assert p not in proxy_settings, "redefining protocol proxy server"
                t2 = { 'proxy': uri }
                t2.update(global_sets)

                proxy_settings[p] = t2

        my_subcfg['proxy_settings'] = proxy_settings

        # normalize proxy auth
        proxy_auth = my_subcfg.get('auth', None)

        if proxy_auth:

            normed_proxy_auth = {}
            default_auth = {}

            if 'username' in proxy_auth:
                # assume flat user, password def for all proxy types
                default_auth = proxy_auth

            for (prot, pxset) in iteritems(proxy_servers):

                uri = pxset['uri']
                tmp = copy.deepcopy(proxy_auth.get(prot, default_auth))

                pxset.update({
                  'auth': {
                    'user': tmp['username'],
                    'password': tmp['secret'],
                  }
                })

                if uri in normed_proxy_auth:
                    ## if one server is used for multiple protocols 
                    ## we obviously need it only once
                    continue

                tmp.update({
                  'type': 'generic_password',
                  'state': 'present',
                  'name': urlparse(uri).hostname,
                })

                normed_proxy_auth[uri] = tmp

            my_subcfg['auth'] = normed_proxy_auth

        return my_subcfg


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

