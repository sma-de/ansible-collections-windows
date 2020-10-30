
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import re

from ansible.errors import AnsibleOptionsError, AnsibleError##, AnsibleModuleError##
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.ldap.base import LdapConnection
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible.utils.display import Display


display = Display()


class WinADConnection(LdapConnection):

    @property
    def domain_user(self):
        tmp = self.user.split('\\')

        if len(tmp) < 2:
            ansible_assert(self.domain, 
               "bad winad domain user, either give user as complete"\
               " domain user ('domain\\user') or set domain parameter"
            )

            tmp = [self.domain] + tmp

        return '\\'.join(tmp)


    def rebind(self, **kwargs):
        import ldap3
        kwargs.setdefault('authentication', ldap3.NTLM)
        kwargs['user'] = self.domain_user
        return super(WinADConnection, self).rebind(**kwargs)


    def change_pw(self, newpw, connection=None, user=None, oldpw=None):
        connection = connection or self.default_connection

        ## if no user is specified, use default auth user
        if not user:
            user = self.upn
            oldpw = self.usrpw
        else:
            ansible_assert(oldpw, 'if you set user, you also must set oldpw')

        if oldpw == newpw:
            return False

        uo = self.get_user_object(connection=connection, user=user, empty_match_error=True)

        display.vv(
           "WinAD :: change pw :: found matching user object: " + str(uo)
        )

        import ldap3
        if not ldap3.extend.microsoft.modifyPassword.ad_modify_password(
           connection, uo['dn'], newpw, oldpw, controls=None):

            errmsg = \
               "failed to change win-ad password for user '{}'".format(user)

            res = connection.result

            if re.search(r'(?i) Operation not allowed through GC port', res['message']):
                errmsg += \
                  '(possible reasons: connect to server using insecure'\
                  ' / non-ssl port (upgrading the connection later with'\
                  ' start_tls does not help))'

            elif res.get('description', '').lower() == 'unwillingtoperform':
                errmsg += \
                  '(possible reasons: new password does not comply with'\
                  ' password complexity policy)'

            elif res.get('description', '').lower() == 'constraintviolation':
                errmsg += \
                  '(possible reasons: trying to re-use a previous'\
                  ' password, password to young (it is not unusual'\
                  ' that you must wait for example one or two days'\
                  ' before changing password again))'

            errmsg += ', details: ' + str(res)
            raise AnsibleError(errmsg)

        return True

