
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import json
import re

from ansible.errors import AnsibleModuleError##, AnsibleError,AnsibleOptionsError, 
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWinPowerCmdDataReturn
from ansible_collections.smabot.windows.plugins.module_utils.utils.powershell import to_pshell_array_param
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


##COMMAND_TYPES = {
##  32: 'Application',
##}


ENUM_MAPPING_DIRECTION = {
  1: 'in',
}

ENUM_MAPPING_ACTION = {
  2: 'allow',
}

ENUM_MAPPING_ENABLED = {
  1: True,
}


def create_map_enum_mapper(mapping_id, mapping):
    def map_enum_map(val):
        tmp = mapping.get(val, None)

        if tmp is None:
            raise AnsibleModuleError(
               "Unknown enum mapping value '{}' for '{}':"\
               " {}".format(mapping_id, val, mapping)
            )

        return tmp

    return map_enum_map


## the concept behind the mapping here is that the format 
## returned can be 1:1 used as input for ansible win 
## firewall management module
KEY_FILTERS = {
  ## left value => returned by windows
  ## right value => how it should be exported to ansible, on default this is lvalue.lower()
  'rule': {
    'Name': None,
    'Description': None,

    'Action': (None, 
       create_map_enum_mapper('ACTION', ENUM_MAPPING_ACTION)
    ),

    'Direction': (None, 
       create_map_enum_mapper('DIRECTION', ENUM_MAPPING_DIRECTION)
    ),

    'Enabled': (None, 
       create_map_enum_mapper('ENABLED', ENUM_MAPPING_ENABLED)
    ),
  },

  'port': {
    'Protocol':    (None, lambda x: x.lower()),
    'LocalPort':   (None, lambda x: x.lower()),
    'RemotePort':  (None, lambda x: x.lower()),
  },
}



## TODO: handle ip's and the rest of the parameters avaible
class ActionModule(ActionBaseWinPowerCmdDataReturn):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False
        self._final_cmd = None


    def _create_fwall_query(self, query):
        cmd = ['Get-NetFirewallRule']

        cmd.append('-Name')
        cmd.append(to_pshell_array_param(query))

        return ' '.join(cmd)


    @property
    def final_cmd(self):
        tmp = self._final_cmd

        if tmp:
            return tmp

        self._final_cmd = self._create_fwall_query(
          self.get_taskparam('search_query')
        )

        return self._final_cmd

    @property
    def return_key(self):
        return 'matches'

    @property
    def return_key_single(self):
        return 'rule'

    @property
    def extra_args(self):
        tmp = super(ActionModule, self).extra_args

        ##tmp.update({
        ##   'keyfilter': ['Name'] + self.get_taskparam('keyfilter'),

        ##   ## detecting non existant programs is a normal feature 
        ##   ## of this, not an error
        ##   'ignore_error': True, 
        ##})

        return tmp

    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'search_query': (list(string_types) + [list(string_types)]),
        })

        return tmp


    def _handle_keyfiltering(self, subtype, json_in, resmap):
       for k,v in KEY_FILTERS[subtype].items():
           try:
               key_conv, val_conv = v
           except TypeError:
               key_conv = v
               val_conv = None

           if key_conv:
               if callable(key_conv):
                   nk = key_conv(k)
               else:
                   ## on default expect replacement string literal
                   nk = key_conv
           else:
               nk = k.lower()

           nv = json_in[k]

           if val_conv:
               nv = val_conv(nv)

           resmap[nk] = nv


    def _postproc_json(self, jsonres):
        if not jsonres:
            return jsonres

        ## in general this can return more than one matching command
        if not isinstance(jsonres, list):
            jsonres = [jsonres]

        res = []
        for jo in jsonres:
            subres = {}
            res.append(subres)

            self._handle_keyfiltering('rule', jo, subres)

            ## note: for port related infos we need to query another 
            ##   command, and the easiest way atm seems to do another 
            ##   call here
            tmp = self.exec_powershell_script(
                 self._create_fwall_query(subres['name']) \
               + ' | Get-NetFirewallPortFilter', 
               expect_min=1, expect_max=1, force_unlist=True,
               data_return=True,
            )

            self._handle_keyfiltering('port', tmp['result_json'], subres)

        return res

