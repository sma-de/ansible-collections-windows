
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import pathlib

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import \
     ConfigNormalizerBaseMerger, \
     NormalizerBase, \
     key_validator_trueish, \
     DefaultSetterConstant#, DefaultSetterFmtStrCfg, DefaultSetterFmtStrSubCfg

from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SshServerNormalizer(pluginref),
          RemoteFsNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


class SshServerNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(SshServerNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['ssh_server']


class RemoteFsNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'no_autolinking', DefaultSetterConstant(False)
        )

        super(RemoteFsNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['remote_fs']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        real_path = self._get_mandatory_subkey(my_subcfg, 'real_path', 
          cfgpath_abs, validate_fn=key_validator_trueish
        )

        real_path = pathlib.PureWindowsPath(real_path)

        # check that real_path does not exist on target or exists and is dir
        stat = self.pluginref.exec_module(
          'ansible.windows.win_stat', modargs={'path': str(real_path)}
        )

        if stat['stat']['exists'] and not stat['stat']['isdir']:
            raise AnsibleOptionsError(
               "{}: bad 'real_path' parameter value, path already exists"\
               " and is not a directory: {}".format(
                  '.'.join(cfgpath_abs), real_path
               )
            )

        ##
        ## note: on default create a symlink on c drive when remote fs is 
        ##   situated on another drive, because non-c-drive jenkins homes 
        ##   can get easily lead to a lot of problems, like for example 
        ##   like win-docker, which only seems to properly handle volumes 
        ##   on drive c:
        ##
        if not my_subcfg['no_autolinking']:
            link_path = my_subcfg.get('link_path', None)

            real_path_on_c = real_path.drive.lower() == 'c:'

            ## if user explicitly set a link path, use that, if not default it
            if not link_path:

                if real_path_on_c:
                    # real path is on c:, so we dont do linking on default
                    link_path = None
                else:
                    # real path is not on 'c:', we need a symlink on 'c:', 
                    # default to same path as real_path
                    link_path = pathlib.PureWindowsPath('c:\\') \
                              / real_path.relative_to(real_path.anchor)

                    link_path = str(link_path)

            my_subcfg['link_path'] = link_path

            link_path_on_c = \
              pathlib.PureWindowsPath(link_path).drive.lower() == 'c:'

            my_subcfg['_none_on_c'] = not real_path_on_c and not link_path_on_c

        return my_subcfg



class ActionModule(ConfigNormalizerBaseMerger):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self), 
            *args, default_merge_vars=['win_jenkins_sshslave_args_defaults'], 
            extra_merge_vars_ans=['extra_win_jenkins_sshslave_config_maps'], 
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'win_jenkins_sshslave_args'

