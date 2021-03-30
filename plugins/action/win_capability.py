
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import re

from ansible.errors import AnsibleOptionsError, AnsibleError ##, AnsibleModuleError##, AnsibleError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWin
##from ansible_collections.smabot.windows.plugins.module_utils.utils.powershell import to_pshell_array_param
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


CAP_STATES = {
  4: 'INSTALLED',
}


class ActionModule(ActionBaseWin):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'caps': (list(string_types) + [[dict] + list(string_types)]),
          'state': (list(string_types), 'present', ['present', 'absent']),
        })

        return tmp
 

    def _on_getcap_error(self, modres):
        state = self.get_taskparam('state')

        if state == 'absent':
            # nothing to do when state is absent
            return False

        err = modres['stderr']

        tmp = re.search(
          r'(?i)(fehlercode|errorcode):\s+(0x[a-fA-F0-9]+)', err
        )

        if tmp:
            ## set a special more meaningful error msg for specific errrors
            tmp = int(tmp.group(2), 16)

            ## somewhat hard to find, but it seems possible to disable 
            ## machine local installation of windows capabilities by domain 
            ## policies or similar, which probably make sense, which than 
            ## results in this non-saying error code when calling "Get-Caps"
            if tmp == 0x8024002e:
                modres['msg'] = "Could not query external windows"\
                   " capability sources, maybe installation of capabilities"\
                   " is disabled by administrator or domain policy"
                return False

        return False


    def run_specific(self, result):
        caps = self.get_taskparam('caps')
        state = self.get_taskparam('state')

        ## normalize caps arg
        if not isinstance(caps, list):
            ## assume single string
            caps = [caps]

        tmp = []

        for c in caps:
            if not isinstance(c, collections.abc.Mapping):
                ## assume single string which represents name (plus optional meta)
                c = c.split('~')

                nc = { 'name': c[0] }

                if len(c) > 1:
                    nc.update(locale=c[3], version=c[4])

                c = nc

            tmp.append(c)

        caps = tmp

        cap_info = {}
        restart_needed = False

        for c in caps:
            cap_name = [c['name']]
            name_suffix = []

            if 'locale' in c:
                name_suffix.append(c['locale'])

            if 'version' in c:
                name_suffix.append(c['version'])

            if name_suffix:
                name_suffix = ['', ''] + name_suffix

            cap_name = '~'.join(cap_name + name_suffix)

            ##
            ## check if caps are already installed
            ##
            cmd = ['Get-WindowsCapability', '-Online', '-Name', cap_name]

            if state == 'absent':
                ##
                ## note: LimitAccess is an important parameter here, because 
                ##   it possible that because of AD/Domain restrictions 
                ##   installation of capabilities is forbidden, but we can 
                ##   still use this module for removing capabilities, but the 
                ##   thing is that normally just listing caps with "Get-Cap" 
                ##   already errors out when installing is forbidden, as this 
                ##   on default already tries to query online resources for 
                ##   caps, but with the access limit param we actually only 
                ##   query the local machine, which should always be fine
                ##
                cmd += ['-LimitAccess', '| where state -eq "Installed"']

            tmp = self.exec_powershell_script(' '.join(cmd), 
               data_return=True, on_error=self._on_getcap_error
            )

            tmp = tmp['result_json']

            if not tmp:
                if state == 'absent':
                    ## caps we want to remove are not installed, noop
                    continue

                raise AnsibleError(
                   "Failed to install capability for given name '{}':"\
                   " could not match name to capability".format(cap_name)
                )

            ## found installed caps
            if not isinstance(tmp, list):
                ## possible that we find one ore multiple 
                ## matching caps, unify both cases
                tmp = [tmp]

            for ec in tmp:
                cap_info[ec['Name']] = { 'details': ec }

            if state == 'present':
                new_caps = []

                ## filter out already installed caps
                for fc in tmp:
                    if CAP_STATES.get(fc['State'], 'UNKNOWN') != 'INSTALLED':
                        new_caps.append(fc)

                if not new_caps:
                    ## caps we want to install already there, noop
                    continue

                ## install new caps
                if len(tmp) > 1:
                    # TODO: support latest mode where we auto select latest version (but still assert that name base is the same for all possible candidates
                    raise AnsibleOptionsError(
                       "Given caps name '{}' is ambigious (matches more"\
                       " than one capability). For installing caps"\
                       " (state == present) name must match exactly one"\
                       " capability.".format(cap_name)
                    )

                result['changed'] = True
                ansible_assert(False, "TODO: handle installing new caps")
                continue

            ## remove existing caps
            result['changed'] = True

            for ec in tmp:
                cmd = 'Remove-WindowsCapability -Online -Name "{}"'.format(ec['Name'])
                rmres = self.exec_powershell_script(cmd, data_return=True)
                rmres = rmres['result_json']

                cap_info[ec['Name']]['remove'] = rmres

                restart_needed = restart_needed or rmres['RestartNeeded']

        result['capabilities'] = cap_info
        result['restart_needed'] = restart_needed
        return result 

