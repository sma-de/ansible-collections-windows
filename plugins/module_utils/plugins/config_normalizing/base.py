
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleOptionsError
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.base.plugins.module_utils.plugins.config_normalizing.base import ConfigNormalizerBaseMerger
from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWin

##from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert


class ConfigNormalizerBaseMergerWin(ConfigNormalizerBaseMerger, ActionBaseWin):
    pass

