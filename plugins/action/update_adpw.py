
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import re

from ansible.errors import AnsibleOptionsError, AnsibleError##, AnsibleModuleError##
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.ldap.base import LdapActionBase
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.windows.plugins.module_utils.plugins.ldap.win_ad import WinADConnection
from ansible.utils.display import Display


display = Display()


class ActionModule(LdapActionBase):

    TRANSFERS_FILES = False

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, 
            ldap_connection_type=WinADConnection, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'pw_new': (list(string_types)),

          'user': (list(string_types), ''),
          'pw_old': (list(string_types), ''),
        })

        return tmp


    def run_ldap_tasks(self, result):
        result['changed'] = self.ldap_connection.change_pw(
           self.get_taskparam('pw_new'), 
           user=self.get_taskparam('user'), 
           oldpw=self.get_taskparam('pw_old')
        )

        return result

    def cleanup(self, force=False):
        pass

