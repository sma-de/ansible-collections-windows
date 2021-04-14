
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pathlib

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMerger, NormalizerBase, DefaultSetterConstant
##from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.windows.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMergerWin
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none

from ansible_collections.smabot.windows.plugins.action import command_info



def shell_type_match_cmdbat(command):
    if command.endswith('windows\\system32\\cmd.exe'):
        print(",aaatch")
        return 'cmdbat'

    return None

def shell_type_match_powershell(command):
    if command.endswith('powershell.exe'):
        return 'powershell'

    return None

def shell_type_match_winbash(command):
    if command.endswith('windows\\system32\\bash.exe'):
        return 'winbash'

    return None

def shell_type_match_gitbash(command):
    ## note: this is somewhat ambigious here, could also match propably cygwin or mingw, on the other site this path is way to specific I think: "C:\Program Files\Git\bin\bash.exe"
    if command.endswith('\\bin\\bash.exe'):
        return 'gitbash'

    return None


shell_type_matchers = [
  shell_type_match_cmdbat,
  shell_type_match_powershell,
  shell_type_match_winbash,
  shell_type_match_gitbash,
]


def get_shell_type(command):
    for stm in shell_type_matchers:
        res = stm(command)

        if res:
            return res

    return 'custom'


class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ShellNormalizer(pluginref),
          FirewallNormalizer(pluginref),
          ServiceNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


class ShellNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'command', DefaultSetterConstant('*Windows\\System32\\cmd.exe')
        )

        self._add_defaultsetter(kwargs, 
           'use_profiling', DefaultSetterConstant(True)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ShellProfilingNormalizer(pluginref),
        ]

        super(ShellNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['shell']


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ## normalize command spec to absolute binary path
        cmd = my_subcfg['command']

        tmp = {
          'command': cmd,
          'type': 'Application',
        }

        tmp = self.pluginref.run_other_action_plugin(
          command_info.ActionModule, plugin_args=tmp
        )

        tmp = tmp['command_info']

        if tmp:

            if len(tmp) > 1:
                raise AnsibleOptionsError(
                  "Given shell command specifier '{}' was ambiguos. It must"\
                  " uniquely identify a single application on target.".format(cmd)
                )

            cmd = tmp[0]['Path']

        else:

            if not pathlib.PureWindowsPath(cmd).is_absolute():
                raise AnsibleOptionsError(
                   "Given shell command specifier '{}' did not match anything"\
                   " on target. Make sure the application is installed and"\
                   " that command specifier is correct.".format(cmd)
                )

            stat = self.pluginref.exec_module(
               'ansible.windows.win_stat', modargs={'path': cmd}
            )

            if not stat['stat']['exists']:
                raise AnsibleOptionsError(
                   "Given shell command specifier absolute path '{}'"\
                   " does not exist on target. Make sure the"\
                   " application is installed and the path is"\
                   " correct.".format(cmd)
                )

            if stat['stat']['isdir']:
                raise AnsibleOptionsError(
                   "Given shell command specifier absolute path '{}'"\
                   " is a directory not an application, check your"\
                   " path.".format(cmd)
                )

            # path is not recognized by powershell as application, 
            # but it is absolute, does exits, is no dir etc., so 
            # we will allow it as it is unchanged

        my_subcfg['command'] = cmd

        setdefault_none(my_subcfg, 'type', get_shell_type(cmd.lower()))
        return my_subcfg


    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        tmp = my_subcfg['profiling_args']['profiling_scripts']['paths']

        if not tmp:
            my_subcfg['use_profiling'] = False

        return my_subcfg


class ShellProfilingNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          ShellProfilingSubScriptsNormalizer(pluginref),
        ]

        super(ShellProfilingNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['profiling_args']


## TODO: does it make sense like this, or do we need special subclasses for different shells here??
class ShellProfilingSubScriptsNormalizer(NormalizerBase):


    def __init__(self, pluginref, *args, **kwargs):
        super(ShellProfilingSubScriptsNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['profiling_scripts']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        shell_type = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        shell_type = shell_type['type']

        paths = setdefault_none(my_subcfg, 'paths', {})

        tmp = pathlib.PosixPath(self.pluginref.get_ansible_var('role_path')) \
            / 'templates' / 'shell_profiling' / shell_type

        if tmp.exists():
            tmp = str(tmp) + '/'
            paths[tmp] = None

        return my_subcfg


class FirewallNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'state', DefaultSetterConstant('present')
        )

        self._add_defaultsetter(kwargs, 
           'enabled', DefaultSetterConstant(True)
        )

        super(FirewallNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['firewall']



class ServiceNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'state', DefaultSetterConstant('started')
        )

        self._add_defaultsetter(kwargs, 
           'password', DefaultSetterConstant('')
        )

        super(ServiceNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['service']



class ActionModule(ConfigNormalizerBaseMergerWin):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self), 
            *args, ##default_merge_vars=['jenkins_slave_args_defaults'], 
            ##extra_merge_vars_ans=['extra_win_jenkinsslave_config_maps'], 
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'winbuiltin_sshserver_args'

    @property
    def supports_merging(self):
        return False

    @property
    def allow_empty(self):
        return True

