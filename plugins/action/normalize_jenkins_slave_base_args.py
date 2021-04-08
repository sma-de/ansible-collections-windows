
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pathlib

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMerger, NormalizerBase, DefaultSetterConstant, DefaultSetterFmtStrCfg, DefaultSetterFmtStrSubCfg
from ansible_collections.smabot.base.plugins.module_utils.utils.dicting import setdefault_none

from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert



class ConfigRootNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          JavaNormalizer(pluginref),
        ]

        super(ConfigRootNormalizer, self).__init__(pluginref, *args, **kwargs)


class JavaNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          JavaDefaultsNormalizer(pluginref),
        ]

        super(JavaNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['java']


class JavaDefaultsNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'enable', DefaultSetterConstant(False)
        )

        ## on default activate all features
        self._add_defaultsetter(kwargs, 
           'default_features', DefaultSetterConstant([
              'FeatureMain',  ## Core AdoptOpenJDK installation (DEFAULT)
              'FeatureEnvironment',  ## Update the PATH environment variable (DEFAULT)
              'FeatureJarFileRunWith',  ## Associate .jar files with Java applications (DEFAULT)
              'FeatureJavaHome',  ## Update the JAVA_HOME environment variable
              'FeatureIcedTeaWeb',  ## Install IcedTea-Web
              'FeatureJNLPFileRunWith',  ## Associate .jnlp files with IcedTea-web
              'FeatureOracleJavaSoft',
           ])
        )

        self._add_defaultsetter(kwargs, 
           'features', DefaultSetterConstant(None)
        )

        subnorms = kwargs.setdefault('sub_normalizers', [])
        subnorms += [
          JavaDefaultsArgsNormalizer(pluginref),
        ]

        super(JavaDefaultsNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['default_java']


class JavaDefaultsArgsNormalizer(NormalizerBase):

    def __init__(self, pluginref, *args, **kwargs):
        self._add_defaultsetter(kwargs, 
           'name', DefaultSetterConstant('adoptopenjdk8jre')
        )

        self._add_defaultsetter(kwargs, 
           'state', DefaultSetterConstant('latest')
        )

        super(JavaDefaultsArgsNormalizer, self).__init__(
           pluginref, *args, **kwargs
        )

    @property
    def config_path(self):
        return ['args']

    def _handle_specifics_presub(self, cfg, my_subcfg, cfgpath_abs):
        pacfg = self.get_parentcfg(cfg, cfgpath_abs)

        inst_args = {}
        inst_args.update(pacfg.get('install_args', {}))

        feats = pacfg['features']

        if not feats:
            feats = pacfg['default_features'][:]

        inst_args['ADDLOCAL'] = ','.join(feats)

        tmp = ''

        for (k,v) in iteritems(inst_args):
            tmp += "{}={}".format(k, v)

        my_subcfg['install_args'] = tmp

        return my_subcfg



class ActionModule(ConfigNormalizerBaseMerger):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(ConfigRootNormalizer(self), 
            *args, **kwargs
        )

        self._supports_check_mode = False
        self._supports_async = False


    @property
    def my_ansvar(self):
        return 'jenkins_slave_base_args'

    @property
    def supports_merging(self):
        return False

    @property
    def allow_empty(self):
        return True

