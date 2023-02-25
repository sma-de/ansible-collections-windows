
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import abc
import copy
import collections

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import NormalizerBase, NormalizerNamed, DefaultSetterConstant
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none, merge_dicts, SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.windows.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMerger



## different distros use diffrent name schemes for pam files,
## add overwrites here when necessary
DISTRO_PAMFILE_OVERWRITES = {
  ##"distro name as returned by ansible_distribution": "pam-file-name"
  ## TODO: fill when suporting another distro
}


class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'fqdn', DefaultSetterConstant(True)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          JoinConfigNormer(pluginref),
          JoinRetryNormer(pluginref),
          SssdNormer(pluginref),
          UserNormer(pluginref),
          NtpNormer(pluginref),
          OsPackagesNormer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


class OsPackagesNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(OsPackagesNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['os_packages']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        export_cfg = {}

        export_cfg['packages'] = self.pluginref.get_ansible_var(
          'smabot_adjoin_os_packages'
        )

        my_subcfg['_export'] = export_cfg
        return my_subcfg


class NtpNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'enabled', DefaultSetterConstant(True)
        )

        super(NtpNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['ntp']

    @property
    def simpleform_key(self):
        return 'enabled'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        nc = setdefault_none(my_subcfg, 'ntp', {})
        setdefault_none(nc, 'enabled', my_subcfg.pop('enabled'))

        return my_subcfg


class UserNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'auto_homedir', DefaultSetterConstant(True)
        )

        self._add_defaultsetter(kwargs,
           'pw_login_ssh', DefaultSetterConstant({'disabled': True})
        )

        self._add_defaultsetter(kwargs,
           'restrict_login', DefaultSetterConstant({'disabled': True})
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          UserSudoNormer(pluginref),
          UserAutoHomeNormer(pluginref),
          UserSshPwLoginNormer(pluginref),
          UserLoginRestrictNormer(pluginref),
        ]

        super(UserNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['users']


class UserLoginRestrictNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'enabled', DefaultSetterConstant(True)
        )

        self._add_defaultsetter(kwargs,
           'method', DefaultSetterConstant('realmd')
        )

        super(UserLoginRestrictNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['restrict_login']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)

        tmp = my_subcfg.get('restrictions', None)

        # dont restrict local users on default
        setdefault_none(tmp, 'local_users', False)

        if tmp:
            for x in ['allow', 'deny']:
                t2 = tmp.get(x, None)

                if not t2:
                    continue

                for y in ['users', 'groups']:
                    t3 = t2.get(y, None)

                    if not t3:
                        continue

                    for k in t3.keys():
                        v = t3[k] or {}
                        t3[k] = v
                        setdefault_none(v, 'domain', pcfg['domain'])

        return my_subcfg


class UserSudoNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          UserSudoUserNormer(pluginref),
          UserSudoGroupNormer(pluginref),
        ]

        super(UserSudoNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['sudoers']

    def _handle_specifics_postsub(self, cfg, my_subcfg, cfgpath_abs):
        export_ids = []

        for k,v in my_subcfg['users'].items():
            export_ids.append(v)

        for k,v in my_subcfg['groups'].items():
            export_ids.append(v)

        my_subcfg['_identities'] = export_ids
        return my_subcfg



class UserSudoIdentityNormer(NormalizerNamed):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'enabled', DefaultSetterConstant(True)
        )

        self._add_defaultsetter(kwargs,
           'ask_pw', DefaultSetterConstant(True)
        )

        super(UserSudoIdentityNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return [self.idtype + 's', SUBDICT_METAKEY_ANY]

    @property
    def simpleform_key(self):
        return 'enabled'

    @property
    def name_key(self):
        return 'id'

    @property
    @abc.abstractmethod
    def idtype(self):
        pass


    def _norm_sudo_fname(self, value):
        # note: sudo is somewhat picky about filenames inside sudoers.d, filter out bad chars
        bad_chars = ['.', '@']

        for x in bad_chars:
            value = value.replace(x, '_')

        return value


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=4)

        ## auto attach domain to user/group names when fully
        ## qualified is requested as it is necessary then
        if pcfg['fqdn']:
            my_subcfg['id'] = my_subcfg['id'] + '@' + pcfg['domain']

        mcfg = setdefault_none(my_subcfg, 'config', {})

        setdefault_none(mcfg, 'name',
           self._norm_sudo_fname(
              "50_adsudo_{}_{}".format(self.idtype, my_subcfg['id'])
           )
        )

        setdefault_none(mcfg, self.idtype, my_subcfg['id'])
        setdefault_none(mcfg, 'nopassword', not my_subcfg['ask_pw'])
        setdefault_none(mcfg, 'commands', 'ALL')

        if my_subcfg['enabled']:
            mcfg['state'] = 'present'
        else:
            mcfg['state'] = 'absent'

        return my_subcfg


class UserSudoUserNormer(UserSudoIdentityNormer):

    @property
    def idtype(self):
        return 'user'


class UserSudoGroupNormer(UserSudoIdentityNormer):

    @property
    def idtype(self):
        return 'group'


class UserAutoHomeNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(UserAutoHomeNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['auto_homedir']

    @property
    def simpleform_key(self):
        return 'enabled'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ahc = setdefault_none(my_subcfg, 'config', {})

        ## pam file name can differ between distros
        pamfile = DISTRO_PAMFILE_OVERWRITES.get(
           self.pluginref.get_ansible_var('ansible_distribution'),
           'common-session' # current default is based on modern ubuntu
        )

        setdefault_none(ahc,        'name', pamfile)
        setdefault_none(ahc,        'type', 'session')
        setdefault_none(ahc,     'control', 'optional')
        setdefault_none(ahc, 'module_path', 'pam_mkhomedir.so')

        if my_subcfg['enabled']:
            ahc['state'] = 'updated'

            setdefault_none(ahc, 'new_type', ahc['type'])
            setdefault_none(ahc, 'new_control', ahc['control'])
            setdefault_none(ahc, 'new_module_path', ahc['module_path'])
        else:
            ahc['state'] = 'absent'

        return my_subcfg


class UserSshPwLoginNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(UserSshPwLoginNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['pw_login_ssh']

    @property
    def simpleform_key(self):
        return 'enabled'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        sshcfg = setdefault_none(my_subcfg, 'config', {})

        setdefault_none(sshcfg,  'path', '/etc/ssh/sshd_config')
        setdefault_none(sshcfg, 'regex', r'^#?\s*PasswordAuthentication\s*\w+')
        sshcfg['state'] = 'present'

        if my_subcfg['enabled']:
            sshcfg['line'] = 'PasswordAuthentication yes'
        else:
            sshcfg['line'] = 'PasswordAuthentication no'

        return my_subcfg



class JoinConfigNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'state', DefaultSetterConstant('present')
        )

        super(JoinConfigNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['join', 'config']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pcfg = self.get_parentcfg(cfg, cfgpath_abs, level=2)
        my_subcfg['domain'] = pcfg['domain']
        return my_subcfg


class JoinRetryNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'num', DefaultSetterConstant(4)
        )

        self._add_defaultsetter(kwargs,
           'delay', DefaultSetterConstant(30)  # unit is seconds
        )

        super(JoinRetryNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['join', 'retries']


class SssdNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'pam_account', DefaultSetterConstant({'disabled': True})
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SssdPamAccNormer(pluginref),
          SssdConfigNormer(pluginref),
        ]

        super(SssdNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['sssd']


class SssdPamAccNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(SssdPamAccNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['pam_account']

    @property
    def simpleform_key(self):
        return 'enabled'

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        mcfg = setdefault_none(my_subcfg, 'config', {})

        ## pam file name can differ between distros
        pamfile = DISTRO_PAMFILE_OVERWRITES.get(
           self.pluginref.get_ansible_var('ansible_distribution'),
           'common-account' # current default is based on modern ubuntu
        )

        setdefault_none(mcfg,        'name', pamfile)
        setdefault_none(mcfg,        'type', 'account')
        setdefault_none(mcfg,     'control', '[default=bad success=ok user_unknown=ignore]')
        setdefault_none(mcfg, 'module_path', 'pam_sss.so')

        setdefault_none(mcfg,        'new_type', mcfg['type'])
        setdefault_none(mcfg,     'new_control', mcfg['control'])
        setdefault_none(mcfg, 'new_module_path', mcfg['module_path'])

        if my_subcfg['enabled']:
            mcfg['state'] = 'updated'
        else:
            mcfg['state'] = 'absent'

        return my_subcfg


class SssdConfigNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs,
           'base_template', DefaultSetterConstant(None)
        )

        self._add_defaultsetter(kwargs,
           'path', DefaultSetterConstant('/etc/sssd/sssd.conf')
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SssdConfigExtraOptsNormer(pluginref),
        ]

        super(SssdConfigNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['config']


class SssdConfigExtraOptsNormer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(SssdConfigExtraOptsNormer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['extra_options']

    def _create_exportcfg_element(self, sectname, optkey, optvals, **common_opts):
        if not isinstance(optvals, collections.abc.Mapping):
            k = 'value'

            if isinstance(optvals, list):
                k = 'values'

            optvals = {
              k: optvals
            }

        res = merge_dicts(copy.deepcopy(common_opts), optvals)
        res.update(
          section=sectname, option=optkey
        )

        return res


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        genopts = setdefault_none(my_subcfg, 'generic', {})

        ##
        ## note: on default nss and pam service are enabled in the realm config,
        ##   it is not that we dont want to use them but that on modern systems
        ##   this services are actually reachable by on demand systemd socket
        ##   activation and having them additionally directly loaded as modules
        ##   here leads to errors
        ##
        setdefault_none(setdefault_none(genopts, 'services', {}), 'state', 'absent')

        domopts = setdefault_none(my_subcfg, 'domains', {})

        ## normalize config options and create and export config fitted for receiving module
        exportcfg = []

        common_defaults = {
          'state': 'present',
          'exclusive': 'true',
          'path': self.get_parentcfg(cfg, cfgpath_abs).get('path'),
        }

        for k, v in genopts.items():
            exportcfg.append(self._create_exportcfg_element(
               'sssd', k, v, **common_defaults)
            )

        for domname, domvals in domopts.items():

            # add domain specific default optsets

            # should also be upstream default, but to be safe than sorry
            # assure enumerate is not done on default as it is recommended,
            # see also: https://docs.pagure.org/sssd.sssd/users/faq.html'
            setdefault_none(domvals, 'enumerate', False)

            for k, v in domvals.items():
                exportcfg.append(self._create_exportcfg_element(
                   "domain/{}".format(domname), k, v, **common_defaults)
                )

        my_subcfg['_export'] = exportcfg
        return my_subcfg



class ActionModule(ConfigNormalizerBaseMerger):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self), 
            *args,
            default_merge_vars=['smabot_windows_linux_adjoin_args_defaults'],
##            extra_merge_vars_ans=['extra_smabot_win_inet_basics_args_config_maps'],
            **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'smabot_windows_linux_adjoin_args'

