
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import json
import pathlib


from ansible.errors import AnsibleOptionsError, AnsibleError ##, AnsibleModuleError##, AnsibleError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWin
##from ansible_collections.smabot.windows.plugins.module_utils.utils.powershell import to_pshell_array_param
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible.utils.display import Display

from ansible_collections.ansible.windows.plugins.action import win_copy


display = Display()


class ActionModule(ActionBaseWin):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        subspec_cfg_access = {
          'group_name': (list(string_types), ''),
          'users': ([list(string_types)], []),
        }

        subspec_cfg = {
          'access': ([collections.abc.Mapping], {}, subspec_cfg_access),
          'daemon': ([collections.abc.Mapping], {}),
        }

        tmp.update({
          'config': ([collections.abc.Mapping], {}, subspec_cfg),
          'state': (list(string_types), 'present', ['present', 'absent']),
        })

        return tmp


##        display.vv(
##           "[FS_LINK] :: queried link path stat: {}".format(link_stat)
##        )


    def _get_dockinfo(self, result):
        return result.setdefault('info', {}).setdefault('docker', {})

    def _get_need_dock_restart(self, result):
        return self._get_dockinfo(result).get('needs_restart', False)

    def _set_need_dock_restart(self, result):
        tmp = self._get_dockinfo(result)
        tmp['needs_restart'] = True


    def _handle_config(self, docker_dir, result):
        config = self.get_taskparam('config')

        if not config:
            return result 

        cfg_daemon = config['daemon']
        cfg_access = config['access']

        if cfg_access:
            grp = cfg_access['group_name']
            users = cfg_access['users']

            if not grp:
                raise AnsibleOptionsError("Must set access group_name")

            if not users:
                raise AnsibleOptionsError("Must set access users")

            cfg_daemon['group'] = grp

            # make sure group exists ...
            tmp = self.exec_module('ansible.windows.win_group', modargs={
                'name': grp, 'state': 'present', 
                'description': 'Controls who is allowed to run docker on this machine'
              }
            )

            if tmp['changed']:
                result['changed'] = True
                self._set_need_dock_restart(result)

            # ... and has all the users it should have
            tmp = self.exec_module('ansible.windows.win_group_membership', modargs={
                'name': grp, 'state': 'pure', 
                'members': users
              }
            )

            if tmp['changed']:
                result['changed'] = True
                self._set_need_dock_restart(result)

        ddir_cfg = docker_dir / 'config'

        if cfg_daemon:
            ## set daemon json based on given input config
            tmp = ddir_cfg / 'daemon.json'
            tmp = self.run_other_action_plugin(
              win_copy.ActionModule, plugin_args={
                'content': json.dumps(cfg_daemon, indent=3), 
                'dest': str(tmp), 'state': 'present'
              }
            )

            if tmp['changed']:
                ## daemon json has changed
                result['changed'] = True
                self._set_need_dock_restart(result)

        return result 


    def _handle_present(self, result):
        ## (TODO: depens on which win sys, this is for win server, not win10
        ## make sure win container feature is there
        ## make sure win docker is installed

        ## TODO: make this a configurable param??
        docker_dir = self.get_target_envvars(
          key_includes=['ProgramData'], single=True
        )

        docker_dir = pathlib.PureWindowsPath(docker_dir) / 'docker'

        tmp = self._get_dockinfo(result)
        tmp['docker_home'] = str(docker_dir)

        ## handle configuration
        self._handle_config(docker_dir, result)

        if self._get_need_dock_restart(result):
           self.exec_powershell_script('Restart-Service docker')

        return result 


    def _handle_absent(self, result):
        assert False, "TODO: implement absent"
        return result 


    def run_specific(self, result):
        state = self.get_taskparam('state')
        getattr(self, '_handle_' + state)(result)
        return result 

