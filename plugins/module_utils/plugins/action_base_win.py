
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import abc
import json

from ansible.errors import AnsibleModuleError##, AnsibleError, AnsibleOptionsError, 
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.action_base import BaseAction

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert
from ansible.utils.display import Display


display = Display()


class ActionBaseWin(BaseAction):

    def __init__(self, *args, **kwargs):
        super(ActionBaseWin, self).__init__(*args, **kwargs)

    ## note: final command must always be a single command which must 
    ##   return the final result value / object and must be pipeable, 
    ##   if you need to do more than one can senseably fit into a single 
    ##   pipeline, use the optional preprocess param
    def exec_powershell_script(self, finalcmd, preprocess=None, 
        extra_psargs=None, keyfilter=None, keys_exclude=False, 
        data_return=False, expect_min=None, expect_max=None, 
        force_unlist=False, cmd_exe=False, **kwargs
    ):
        script = preprocess or ''

        if script:
            script += '\n'

        # make sure to return result as json
        if data_return:
            script += "{} | ConvertTo-Json".format(finalcmd)
        else:
            script += "{}".format(finalcmd)

        if cmd_exe:
            if len(script.split('\n')) > 1:
                raise AnsibleModuleError(
                  "cmd_exe psmode can only be used for oneliners"
                )

            script = 'cmd /c ' + script

        modargs = extra_psargs or {}

        ## note: _raw_params is the magic internal key for free_form args
        modargs.update(stdin=script, _raw_params='powershell.exe -')

        res = self.exec_module('ansible.windows.win_command', 
          modargs=modargs, **kwargs
        )

        if not data_return:
            return res

        ## note: normally, a subcall failing will immediately abort this 
        ##   plugin, but it is possible, that a subcall failure is deemed 
        ##   acceptable for specific use cases, if that's occure, just 
        ##   return the raw result
        tmp = res['stdout']
        if not tmp:

            if expect_min:
                raise AnsibleModuleError(
                   "Bad powershell script call '{}': Expected at least"\
                   " '{}' items returned, but result was empty".format(
                      finalcmd, expect_min
                   )
                )

            res['result_json'] = {}
            return res

        ## on success we expect stdout to contain valid json result object
        tmp = json.loads(tmp)
        delist = False

        display.vvv(
           "[ACTION_PLUGIN_WIN] :: execute powershell script :: raw"\
           " jsoned results: {}".format(tmp)
        )

        display.vvv(
           "[ACTION_PLUGIN_WIN] :: execute powershell script ::"\
           " json key filter ({1}): {0}".format(keyfilter, 
               'exclude' if keys_exclude else 'include'
           )
        )

        if not isinstance(tmp, list):
            delist = True
            tmp = [tmp]

        if expect_min:
            if expect_max and expect_min > expect_max:
                raise AnsibleModuleError(
                   "Bad powershell script call '{}': Invalid"\
                   " parameters, expect_min ('{}') cannot be greater"\
                   " than expect_max('{}')".format(
                      finalcmd, expect_min, expect_max
                   )
                )

            if len(tmp) < expect_min:
                raise AnsibleModuleError(
                   "Bad powershell script call '{}': Expected at least"\
                   " '{}' items returned, but got only '{}'".format(
                      finalcmd, expect_min, len(tmp)
                   )
                )

        if expect_max and len(tmp) > expect_max:
            raise AnsibleModuleError(
               "Bad powershell script call '{}': Expected at most '{}'"\
               " items returned, but got '{}'".format(
                  finalcmd, expect_max, len(tmp)
               )
            )

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

        if delist or force_unlist:
            if len(tmp) != 1:
                raise AnsibleModuleError(
                   "Bad powershell script call '{}': Delisting json"\
                   " result is only allowed for single element lists,"\
                   " but got '{}' items: {}".format(finalcmd, len(tmp), tmp)
                )

            tmp = tmp[0]

        res['result_json'] = tmp

        display.vvv(
           "[ACTION_PLUGIN_WIN] :: execute powershell script ::"\
           " final json results: {}".format(tmp)
        )

        return res


class ActionBaseWinPowerCommand(ActionBaseWin):

    def __init__(self, *args, **kwargs):
        super(ActionBaseWinPowerCommand, self).__init__(*args, **kwargs)


    @property
    @abc.abstractmethod
    def final_cmd(self):
        pass

    @property
    def extra_args(self):
        return {}


    def run_specific(self, result):
        return self.exec_powershell_script(self.final_cmd, **self.extra_args)



class ActionBaseWinPowerCmdDataReturn(ActionBaseWinPowerCommand):

    def __init__(self, *args, **kwargs):
        super(ActionBaseWinPowerCmdDataReturn, self).__init__(*args, **kwargs)

    @abc.abstractproperty
    def return_key(self):
        pass

    @abc.abstractproperty
    def return_key_single(self):
        pass

    @property
    def argspec(self):
        tmp = super(ActionBaseWinPowerCmdDataReturn, self).argspec

        tmp.update({
          'expect_min': ([int], 0),
          'expect_max': ([int], 0),
        })

        return tmp

    @property
    def extra_args(self):
        tmp = super(ActionBaseWinPowerCmdDataReturn, self).extra_args

        tmp.update({
          'data_return': True,
          'expect_min': self.get_taskparam('expect_min'),
          'expect_max': self.get_taskparam('expect_max'),
        })

        return tmp


    def _postproc_json(self, jsonres):
        return jsonres

    def run_specific(self, result):
        tmp = super(ActionBaseWinPowerCmdDataReturn, self).run_specific(
          result
        )

        tmp = self._postproc_json(tmp['result_json'])
        result[self.return_key] = tmp
        result[self.return_key_single] = None

        if len(tmp) == 1:
            result[self.return_key_single] = tmp[0]

        return result

