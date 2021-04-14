
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import json
import re

##from ansible.errors import AnsibleOptionsError, AnsibleModuleError##, AnsibleError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWinPowerCmdDataReturn
from ansible_collections.smabot.windows.plugins.module_utils.utils.powershell import to_pshell_array_param
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


COMMAND_TYPES = {
  32: 'Application',
}


## command_info
class ActionModule(ActionBaseWinPowerCmdDataReturn):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False
        self._final_cmd = None

    @property
    def final_cmd(self):
        tmp = self._final_cmd

        if tmp:
            return tmp

        cmd = ['Get-Command']

        typ_filter = self.get_taskparam('type')

        if typ_filter:
            cmd += ['-type', to_pshell_array_param(typ_filter)]

        tmp = self.get_taskparam('command')

        if not isinstance(tmp, list):
            tmp = [tmp]

        com_query = []

        ##
        ## note: the underlying get-command ps cmdlet does not like path 
        ##   info in its queries, but we will support it by removing 
        ##   prefix paths first and filter later with them
        ##
        path_filter = []
        path_filter_all_match = []

        for cmd_test in tmp:
            t2 = cmd_test.split('\\')

            if len(t2) > 1:
                com_query.append(t2[-1])
                path_filter.append(cmd_test)
            else:
                com_query.append(cmd_test)

                if cmd_test[0] == '*':
                    path_filter_all_match.append(cmd_test)
                else:
                    path_filter_all_match.append('*' + cmd_test)

        cmd.append(to_pshell_array_param(com_query))

        self._final_cmd = ' '.join(cmd)

        if path_filter:
            path_filter += path_filter_all_match

            t2 = []

            for pf in path_filter:
                t2.append("( $_.Source -like '{}' )".format(pf))

            path_filter = ' -or '.join(t2)
            self._final_cmd += ' | Where-Object {{ {} }}'.format(path_filter)

        return self._final_cmd

    @property
    def return_key(self):
        return 'command_info'

    @property
    def return_key_single(self):
        return 'command_info_single'


    @property
    def extra_args(self):
        tmp = super(ActionModule, self).extra_args

        tmp.update({
           'keyfilter': ['Name'] + self.get_taskparam('keyfilter'),

           ## detecting non existant programs is a normal feature 
           ## of this, not an error
           'ignore_error': True, 
        })

        return tmp

    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'command': (list(string_types) + [list(string_types)]),
          'type': (list(string_types) + [list(string_types)], []),

           ## note: powershell json can actually be quite verbose, 
           ##   but we only need a few keys here normally
          'keyfilter': ([list(string_types)], 
              ['Path', 'Extension', 'Version', 'CommandType']
          ),
        })

        return tmp


    def _postproc_json(self, jsonres):
        if not jsonres:
            return jsonres

        ## in general this can return more than one matching command
        if not isinstance(jsonres, list):
            jsonres = [jsonres]

        res = []
        for jo in jsonres:

            ## note: for some reason powershell prefer to return stuff 
            ##   like command type as non-saying integer id's in json 
            ##   instead of strings like "Application", fix this here
            if 'CommandType' in jo:
                ct = jo['CommandType']
                tmp = COMMAND_TYPES.get(ct, None)

                ansible_assert(tmp, "Unsupported CommandType: {}".format(ct))

                jo['CommandType'] = tmp

            res.append(jo)

        return res

