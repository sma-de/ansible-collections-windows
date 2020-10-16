
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


## ##from ansible.errors import AnsibleOptionsError, AnsibleModuleError##, AnsibleError
## ####from ansible.module_utils._text import to_native
## from ansible.module_utils.six import iteritems, string_types


def to_pshell_array_param(val):
    if not isinstance(val, list)
        val = [val]

    return ','.join(val)

