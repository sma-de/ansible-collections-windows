
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import json
import pathlib


from ansible.errors import AnsibleOptionsError, AnsibleError ##, AnsibleModuleError##, AnsibleError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWin
from ansible_collections.smabot.windows.plugins.action import command_info
from ansible_collections.smabot.windows.plugins.module_utils.utils.os_versions import target_is_win_server_os
##from ansible_collections.smabot.windows.plugins.module_utils.utils.powershell import to_pshell_array_param
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible.utils.display import Display

from ansible_collections.ansible.windows.plugins.action import win_copy
from ansible_collections.ansible.windows.plugins.action import win_reboot


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

        ## TODO: support installation of specific versions??
        tmp.update({
          'config': ([collections.abc.Mapping], {}, subspec_cfg),
          'state': (list(string_types), 'present', ['present', 'absent', 'latest']),
        })

        return tmp


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

        cfg_change = False

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
                cfg_change = True
                result['changed'] = True
                self._set_need_dock_restart(result)

            # ... and has all the users it should have
            tmp = self.exec_module('ansible.windows.win_group_membership', modargs={
                'name': grp, 'state': 'pure', 
                'members': users
              }
            )

            if tmp['changed']:
                cfg_change = True
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
                cfg_change = True
                result['changed'] = True
                self._set_need_dock_restart(result)

        if cfg_change:
            tmp = self._get_dockinfo(result)
            tmp['config_changed'] = True

        return result 


    def _handle_install_winserver(self, result):
        display.v(
          "[INSTALL_WINSERVER] :: prepare docker provider and install docker package"
        )

        self.exec_powershell_script(
          'Install-Module -Name DockerMsftProvider -Repository PSGallery -force; '\
          'Install-Package -Name docker -ProviderName DockerMsftProvider -force'
        )


    def _handle_install(self, result):
        tmp = self.run_other_action_plugin(
          command_info.ActionModule, plugin_args={
            'command': 'docker',
            'type': 'Application',
            'expect_min': 1,
          }, ignore_error=True
        )

        if not tmp.get('failed', False):
            display.v(
              "[INSTALL] :: docker already installed => noop"
            )

            return False

        result['changed'] = True

        if target_is_win_server_os(self._ansible_varspace):
            self._handle_install_winserver(result)
        else:
            assert False, "TODO: implement present win10"

        display.display(
           "Freshly installed docker, direct reboot necessary,"\
           " will now begin rebooting ..."
        )

        self.run_other_action_plugin(
          win_reboot.ActionModule, plugin_args={
             # wait after reboot until docker service is ready
             'test_command': 'exit (Get-Service -Name docker).Status -ne "Running"',
          }
        )

        display.display(
           "... rebooting finished, will not continue installation"
        )

        tmp = self._get_dockinfo(result)
        tmp['installed'] = True

        return True


    def _get_docker_version(self, get_cmd='Get-Package'):
        tmp = self.exec_powershell_script(
          get_cmd + ' -Name Docker -ProviderName DockerMsftProvider', 
          data_return=True, keyfilter=['Version']
        )

        return tmp['result_json']['Version']

    def get_currently_installed_docker_version(self):
        return self._get_docker_version()


    def _handle_docker_update(self, result):
        display.vv(
          "[UPDATE] :: check if newer docker version is avaible"
        )

        curver = self.get_currently_installed_docker_version()
        latest_ver = self._get_docker_version(get_cmd='Find-Package')

        ##
        ## note: technically we only check here that both versions differ, 
        ##   theoretically this could also mean that curver is newer than 
        ##   latest_ver, but practically this can never happen, as the 
        ##   call we use to set latest_ver is guaranteed to return the 
        ##   newest version avaible, so if curver is not that version, 
        ##   it must be older
        ##
        if curver == latest_ver:
            ## installed docker is already the newest version, noop
            return

        display.v(
          "[UPDATE] :: docker update found, will now begin updating ..."
        )

        result['changed'] = True

        tmp = self._get_dockinfo(result)
        tmp['updated'] = { 'from': curver }

        self.exec_powershell_script(
          'Install-Package -Name Docker -ProviderName DockerMsftProvider -update -force'
        )

        ## note: it seems after an update of docker restarting 
        ##   the service is sufficient, no reboot needed apparently
        self.exec_powershell_script('Restart-Service docker')

        tmp = self.get_currently_installed_docker_version()
        ansible_assert(tmp == latest_ver, 
           "Updating docker installation from '{}' to '{}'"\
           " failed".format(curver, latest_ver)
        )


    def _handle_present(self, result, docker_datadir, latest=False):
        ## https://docs.microsoft.com/en-us/virtualization/windowscontainers/quick-start/set-up-environment
        ## https://github.com/OneGet/MicrosoftDockerProvider
        display.v(
          "[PRESENT] :: handle installation"
        )

        if not self._handle_install(result) and latest:
            self._handle_docker_update(result)

        tmp = self._get_dockinfo(result)
        tmp['version'] = self.get_currently_installed_docker_version() 

        display.v(
          "[PRESENT] :: handle configuration"
        )

        tmp['docker_home'] = str(docker_datadir)

        ## handle configuration
        self._handle_config(docker_datadir, result)

        if self._get_need_dock_restart(result):
           self.exec_powershell_script('Restart-Service docker')

        return result 


    def _handle_latest(self, result, docker_datadir):
        return self._handle_present(result, docker_datadir, latest=True)


    def _handle_absent_winserver(self, result):
        display.v(
          "[ABSENT_WINSERVER] :: uninstall docker itself"
        )

        ## uninstall docker module and its management provider
        self.exec_powershell_script(
          'Uninstall-Package -Name docker -ProviderName DockerMsftProvider; '\
          'Uninstall-Module -Name DockerMsftProvider'
        )

        display.v(
          "[ABSENT_WINSERVER] :: remove docker default networks"
        )

        ## remove docker default networks
        ## note: this seems to be deprecated even for winserver, it seems to be the same command now also used for win10
        ##self.exec_powershell_script(
        ##  'Get-ContainerNetwork | Remove-ContainerNetwork'
        ##)

        ## TODO: the default windows recommended command seems to remove any kind of hyper-v network here, which seems not ideal considering people could be using them for other purposes than docker, on the other side depends the current solution on the network name being a safe and reliant constanct fact
        self.exec_powershell_script(
          ##'Get-HNSNetwork | Remove-HNSNetwork'
          "Get-HNSNetwork | ? Name -Like 'nat' | Remove-HNSNetwork"
        )

        display.v(
          "[ABSENT_WINSERVER] :: remove windows container feature"
        )

        ## remove win containers feature
        self.exec_module('ansible.windows.win_feature', modargs={
            'name': 'Containers', 'state': 'absent', 
          }
        )

        return result


    def _handle_absent(self, result, docker_datadir):
        tmp = self.exec_module('ansible.windows.win_stat', 
           modargs={'path': str(docker_datadir)}
        )

        if not tmp['stat']['exists']:
            ## docker not installed, noop
            return

        display.vv(
          "[ABSENT] :: initiate docker deinstallation"
        )

        result['changed'] = True
        result['reboot_needed'] = True

        display.v(
          "[ABSENT] :: stop docker service and prune docker system"
        )

        tmp = self.run_other_action_plugin(
          command_info.ActionModule, plugin_args={
            'command': 'docker',
            'type': 'Application',
            'expect_min': 1,
          }, ignore_error=True
        )

        if tmp.get('failed', False):
            ## note: because of a previous unclean, incomplete 
            ##   deinstallation try docker exe might have been 
            ##   removed already, but obviously we still want 
            ##   to go on to achieve a clean and 100% complete 
            ##   deinstallation
            display.warning(
               "Could not prune docker content before deinstallation,"\
               " docker exe could not be found"
            )

        else:
            ## based on this very good article: https://docs.microsoft.com/en-us/virtualization/windowscontainers/manage-docker/configure-docker-daemon
            # -> leave swarm mode (this will automatically stop and remove services and overlay networks)
            # -> stop all running containers
            # -> remove all containers, container images, networks, and volumes
            self.exec_powershell_script(
              'docker swarm leave --force; '\
              'docker ps --quiet | ForEach-Object {docker stop $_}; '\
              'docker system prune --volumes --all -f',
            )

        if target_is_win_server_os(self._ansible_varspace):
            self._handle_absent_winserver(result)
        else:
            assert False, "TODO: implement absent win10"

        display.v(
          "[ABSENT] :: remove docker data dir '{}'".format(docker_datadir)
        )

        ## finally remove docker runtime dir 
        self.exec_module('ansible.windows.win_file', modargs={
            'path': str(docker_datadir), 'state': 'absent', 
          }
        )

        return result 


    def run_specific(self, result):
        ## TODO: make this a configurable param??
        docker_datadir = self.get_target_envvars(
          key_includes=['ProgramData'], single=True
        )

        result['reboot_needed'] = False
        docker_datadir = pathlib.PureWindowsPath(docker_datadir) / 'docker'

        state = self.get_taskparam('state')
        getattr(self, '_handle_' + state)(result, docker_datadir)

        return result 

