
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pathlib

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMerger, NormalizerBase, DefaultSetterConstant, DefaultSetterFmtStrCfg, DefaultSetterFmtStrSubCfg
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'disable_winssh', DefaultSetterConstant(False)
        )

        self._add_defaultsetter(kwargs, 
           'enable_default_java', DefaultSetterConstant(False)
        )

        self._add_defaultsetter(kwargs, 
           'default_java_extra_args', DefaultSetterConstant({})
        )

        self._add_defaultsetter(kwargs, 
           'use_gitbash', DefaultSetterConstant(None)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          JenkinsAgentNormalizer(pluginref),
          ServiceCreateNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        use_gb = my_subcfg['use_gitbash']

        if use_gb:
            use_default = False

            if not isinstance(use_gb, string_types):
                ## if no concrete path is specified, use default path
                use_gb = 'C:\\Program Files\\Git'
                use_default = True

            stat = self.pluginref.exec_module(
               'ansible.windows.win_stat', modargs={'path': use_gb}
            )

            if not stat['stat']['exists'] or not stat['stat']['isdir']:
                tmp = 'user specified'

                if use_default:
                    tmp = 'default'

                raise AnsibleOptionsError(
                   "git-bash {} install path '{}' is invalid, make sure that"\
                   " git-bash is installed before using this role and that"\
                   " the correct install path is used".format(tmp, use_gb)
                )

            my_subcfg['use_gitbash'] = use_gb

        return my_subcfg

class JenkinsAgentNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'default_params', DefaultSetterConstant(True)
        )

        self._add_defaultsetter(kwargs, 
           'params', DefaultSetterConstant([])
        )

        self._add_defaultsetter(kwargs, 'agent_url', 
           DefaultSetterFmtStrSubCfg('{master_url}/jnlpJars/agent.jar')
        )

        self._add_defaultsetter(kwargs, 'node_url', 
           DefaultSetterFmtStrSubCfg(
              '{master_url}/computer/{node_name}/slave-agent.jnlp'
           )
        )

        super(JenkinsAgentNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['agent']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ## handle agent params
        params = my_subcfg['params']

        if my_subcfg['default_params']:
            ## on default activate websocket connection protocoll as 
            ## this is the future and in principle way better than 
            ## old standard mechanism with extra port
            params += ['-webSocket']

        ## make workdir an agent param
        params += ['-workDir', my_subcfg['workdir']]

        my_subcfg['params'] = params
        return my_subcfg


class ServiceCreateNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'name', DefaultSetterConstant('jenkins_slave')
        )

        self._add_defaultsetter(kwargs, 'display_name', 
           DefaultSetterFmtStrCfg('JenkinsSlave {agent[node_name]}')
        )

        self._add_defaultsetter(kwargs, 'description', 
           DefaultSetterFmtStrCfg(
              "Jenkins Slave node '{agent[node_name]}' connected"\
              " to master '{agent[master_url]}'"
           )
        )

        super(ServiceCreateNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['service', 'service', 'create']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        if 'arguments' in my_subcfg:
            raise AnsibleOptionsError(
               "Dont set winservice arguments as they would be"\
               " ignored anyway."
            )

        my_subcfg['arguments'] = [cfg['agent']['secret']]

        gb_path = cfg['use_gitbash']

        if gb_path:
            ## if we use gitbash make sure it is on the path so that stuff 
            ## like ssh-agent can be found by jenkins
            appenv = setdefault_none(my_subcfg, 'app_environment', {})

            tmp = self.pluginref.get_ansible_var('ansible_env')
            t2 = None

            for pv in ['PATH', 'Path']:
                t2 = tmp.get(pv, None)

                if t2:
                    break

            tmp = t2
            assert tmp, "Failed to find $PATH var in environment"

            appenv = tmp \
                + ';' + str(pathlib.PureWindowsPath(gb_path) / 'usr' / 'bin' )

        return my_subcfg


class ActionModule(ConfigNormalizerBaseMerger):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self), 
            *args, default_merge_vars=['jenkins_slave_args_defaults'], 
            extra_merge_vars_ans=['extra_win_jenkinsslave_config_maps'], 
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'jenkins_slave_args'

