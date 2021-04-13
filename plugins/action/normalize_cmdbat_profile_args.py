
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import abc
import collections
import pathlib

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import NormalizerBase, DefaultSetterConstant, DefaultSetterFmtStrCfg, DefaultSetterFmtStrSubCfg
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none, get_subdict
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.windows.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMergerWin


PROFILING_RELDEF_DIR = pathlib.PureWindowsPath('System32') / 'cmdbat'
PROFILING_RELDEF_BASESCRIPT = PROFILING_RELDEF_DIR / 'profile.cmd'
PROFILING_RELDEF_PROFILEDIR = PROFILING_RELDEF_DIR / 'profile.d'


class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'force', DefaultSetterConstant(False)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ProfBaseScriptNormalizer(pluginref),
          ProfDirNormalizer(pluginref),
          ProfScriptsNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        my_subcfg['_target_windir'] = \
           self.pluginref.get_target_envvars(
               key_includes=['windir'], single=True
            )

        return my_subcfg


class ProfScriptsNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(ProfScriptsNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['profiling_scripts']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ## set dest for all given paths to profiling dir
        paths = setdefault_none(my_subcfg, 'paths', {})

        profdir = cfg['profiling_dir']['path'] + '\\'

        for k in list(paths.keys()):
            v = paths[k]

            if isinstance(v, collections.abc.Mapping):
                v['dest'] = profdir
            else:
                v = profdir

            paths[k] = v

        return my_subcfg


class ProfPathNormalizer(NormalizerBase):

    @abc.abstractmethod
    def _get_profsubpath(self):
        pass

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pacfg = self.get_parentcfg(cfg, cfgpath_abs)

        tmp = pathlib.PureWindowsPath(pacfg['_target_windir']) \
            / self._get_profsubpath()

        setdefault_none(my_subcfg, 'path', '{}'.format(tmp))
        setdefault_none(my_subcfg, '_path_quoted', '"{}"'.format(tmp))

        return my_subcfg


class ProfBaseScriptNormalizer(ProfPathNormalizer):

    def __init__(self, pluginref, *args, **kwargs):
        super(ProfBaseScriptNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['profiling_basescript']

    def _get_profsubpath(self):
        return PROFILING_RELDEF_BASESCRIPT


class ProfDirNormalizer(ProfPathNormalizer):

    def __init__(self, pluginref, *args, **kwargs):
        super(ProfDirNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['profiling_dir']

    def _get_profsubpath(self):
        return PROFILING_RELDEF_PROFILEDIR



class ActionModule(ConfigNormalizerBaseMergerWin):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self), 
            *args, ##default_merge_vars=['jenkins_slave_agent_args_defaults'], 
            ##extra_merge_vars_ans=['extra_win_jenkinsslave_agent_config_maps'], 
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_win_cmdbat_profile_args'

    @property
    def supports_merging(self):
        return False

    @property
    def allow_empty(self):
        return True

