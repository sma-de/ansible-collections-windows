
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import json

##from ansible.errors import AnsibleOptionsError, AnsibleModuleError##, AnsibleError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction

##from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, SUBDICT_METAKEY_ANY
##from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert
##from ansible_collections.smabot.containers.plugins.module_utils.common import DOCKER_CFG_DEFAULTVAR


def to_pshell_array_param(val):
    if not isinstance(val, list)
        val = [val]

    return ','.join(val)


class ActionBaseWin(BaseAction):

    def __init__(self, *args, **kwargs):
        super(ActionBaseWin, self).__init__(*args, **kwargs)

    ## note: final command must always be a single command which must 
    ##   return the final result value / object and must be pipeable, 
    ##   if you need to do more than one can senseably fit into a single 
    ##   pipeline, use the optional preprocess param
    def exec_powershell_script(self, finalcmd, preprocess=None, 
        extra_psargs=None, keyfilter=None, keys_exclude=False, **kwargs
    ):
        script = preprocess or ''

        if script:
            script += '\n'

        # make sure to return result as json
        script += "{} | ConvertTo-Json".format(finalcmd)

        modargs = extra_psargs or {}
        modargs.update(cmd='powershell.exe -', stdin=script)

        res = self.exec_module('win_command', modargs=modargs, **kwargs)

        ## note: normally, a subcall failing will immediately abort this 
        ##   plugin, but it is possible, that a subcall failure is deemed 
        ##   acceptable for specific use cases, if that's occure, just 
        ##   return the raw result
        if res.get('failed', False):
            return res

        ## on success we expect stdout to contain valid json result object
        tmp = json.loads(res['stdout'])
        delist = False

        if not isinstance(tmp, list):
            delist = True
            tmp = [tmp]

        ## optionally filter out keys on first level of 
        ## returned dict(s) / json object(s)
        for jo in tmp:
            new_jo = {}

            for k in (keyfilter or []):

                if keys_exclude:
                    jo.pop(k, None)
                elif k in jo:
                    new_jo[k] = jo[k]

            if new_jo:
                jo.clear()
                jo.update(new_jo)

        if delist:
            tmp = tmp[0]

        res['result_json'] = tmp
        return res


class ActionBaseWinPowerCommand(ActionBaseWin):

    def __init__(self, *args, **kwargs):
        super(ActionBaseWinPowerCommand, self).__init__(*args, **kwargs)

    @property
    @abc.abstractmethod
    def final_cmd(self):
        pass

    @property
    @abc.abstractmethod
    def return_key(self):
        pass

    @property
    def extra_args(self):
        return {}

    def _postproc_json(self, jsonres):
        return jsonres

    def run_specific(self, result):
        tmp = self.exec_powershell_script(self.final_cmd, **self.extra_args)
        result[self.return_key] = self._postproc_json(tmp['result_json'])
        return result

