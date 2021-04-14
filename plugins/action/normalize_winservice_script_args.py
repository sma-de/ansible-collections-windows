
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import collections
import pathlib
import os

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBase, NormalizerBase, DefaultSetterConstant
##from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import get_subdict, SUBDICT_METAKEY_ANY

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible_collections.smabot.windows.plugins.action import command_info



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'rootdir', DefaultSetterConstant('C:\\winservices\\script')
        )

        self._add_defaultsetter(kwargs, 
           'interpreter', DefaultSetterConstant('powershell')
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          SourceNormalizer(pluginref),
          ServiceNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


    def _handle_interpreter(self, my_subcfg):
        ## determine abspath for interpreter
        interpreter = my_subcfg['interpreter']

        if pathlib.PureWindowsPath(interpreter).is_absolute():
            return my_subcfg ##noop

        ## if not abspath, assume simple command name, 
        ## normalize to abspath
        tmp = {
          'command': interpreter,
          'type': 'Application',
          ##expect_min: 1,
          expect_max: 1,
        }

        tmp = self.pluginref.run_other_action_plugin(
          command_info.ActionModule, plugin_args=tmp
        )

        tmp = tmp['command_info_single']

        if not tmp:
            raise AnsibleOptionsError(
               "Could not determine abs-path for given interpreter"\
               " '{}'. Make sure that interpreter is installed or"\
               " try to set absolute path to exe"\
               " explicitly.".format(interpreter)
            )

        interpreter = tmp['Path']
        my_subcfg['interpreter'] = interpreter

        return my_subcfg


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        self._handle_interpreter(my_subcfg)

        ## compute dest dir
        destdir = pathlib.PureWindowsPath(my_subcfg['rootdir']) \
                / my_subcfg['service']['service']['name']

        my_subcfg['destdir'] = str(destdir)
        return my_subcfg
 
 
class SourceNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(SourceNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['source']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ## create args for source script dir/file templating
        src_root = my_subcfg['root']
        src = my_subcfg['src']

        if not isinstance(src, collections.abc.Mapping):
            src = { 'src': src }

        src_path = src['src']

        main_script = my_subcfg.get('main_script', None)
        destdir = pathlib.PureWindowsPath(cfg['destdir'])
        destpath = destdir

        sp_abs = pathlib.Path(src_root, 'templates', src_path)

        ## check if src path is valid file or dir
        if not sp_abs.exists():
            raise AnsibleOptionsError(
               "Given script source path '{}' does not exist".format(sp_abs)
            )

        if sp_abs.is_dir():
            ## check if src path is ok
            if src_path[-1] != '/':
                raise AnsibleOptionsError(
                   "We only support copy dir content mode, so source"\
                   " path must end with a slash, set: '{}/'".format(src_path)
                )

            ## check if main script is ok
            if not main_script:
                raise AnsibleOptionsError(
                  "When source is a directory, 'main_script' key must be set"
                )

        else:
            main_script = main_script or os.path.basename(src_path)
            destpath /= main_script

        src['dest'] = str(destpath)
        main_script = destdir / main_script

        cfg['main_script'] = str(main_script)
        cfg['destpath'] = str(destpath)

        templating_args = { 
          'source_root': src_root, 'paths': { src_path: src } 
        }

        cfg['templating_args'] = templating_args
        return my_subcfg


class ServiceNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        super(ServiceNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['service', 'service', 'create']


    def _set_unset_key(self, cfg, key, val, msg_sfx=''):
        if key in cfg:
            raise AnsibleOptionsError(
               "Setting {} key '{}' is not allowed because it is managed"\
               " internally.{}".format('.'.join(self.config_path), key, msg_sfx)
            )
 
        cfg[key] = val


    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        ## set given interpreter as service app
        self._set_unset_key(my_subcfg, 
           'application', cfg['interpreter'], 
           " Use var 'interpreter' instead."
        )

        ## set service working dir to script target dir
        self._set_unset_key(my_subcfg, 'working_directory', cfg['destdir'])

        ## add main script as first service argument
        service_args = my_subcfg.get('arguments', None) or []
        service_args.insert(0, cfg['main_script'])
        my_subcfg['arguments'] = service_args

        return my_subcfg


class ActionModule(ConfigNormalizerBase):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(
            ConfigRootNormalizer(self), *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'winservice_script_args'

    @property
    def supports_merging(self):
        return False

