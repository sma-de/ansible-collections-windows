
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re

## ##from ansible.errors import AnsibleOptionsError, AnsibleModuleError##, AnsibleError
## ####from ansible.module_utils._text import to_native
## from ansible.module_utils.six import iteritems, string_types


def target_is_win_server_os(ansible_varspace):
    ##"ansible_distribution": "Microsoft Windows Server 2019 Standard"

    ## note: this is rather crude, but I could not find anything better yet
    return bool(re.fullmatch(
      r'(?i).*server.*', ansible_varspace['ansible_distribution']
    ))

