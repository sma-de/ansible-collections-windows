
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import pathlib


from ansible.errors import AnsibleOptionsError, AnsibleError ##, AnsibleModuleError##, AnsibleError
####from ansible.module_utils._text import to_native
from ansible.module_utils.six import iteritems, string_types

from ansible_collections.smabot.windows.plugins.module_utils.plugins.action_base_win import ActionBaseWin
##from ansible_collections.smabot.windows.plugins.module_utils.utils.powershell import to_pshell_array_param
from ansible_collections.smabot.base.plugins.module_utils.utils.utils import ansible_assert

from ansible.utils.display import Display


display = Display()



class ActionModule(ActionBaseWin):

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._supports_check_mode = False
        self._supports_async = False


    @property
    def argspec(self):
        tmp = super(ActionModule, self).argspec

        tmp.update({
          'link_path': (list(string_types)),
          'target_path': (list(string_types), ''),
          'overwrite': ([bool], False),
          'force': ([bool], False),
          'state': (list(string_types), 'present', ['present', 'absent']),

          ## TODO: support different types of links: hard, junction, ...
          'link_type': (list(string_types), 'symbolic', ['symbolic']),
        })

        return tmp


    def _query_win_filepath(self, fp, param_name, relpath_root=None):
        fp = pathlib.PureWindowsPath(fp)

        if not fp.is_absolute():
            if not relpath_root:
                raise AnsibleOptionsError(
                   "Invalid param '{}': paths must be absolut, but given"\
                   " value is not: {}".format(param_name, fp)
                )

            fp = pathlib.PureWindowsPath(str(relpath_root)) / fp

        return self.exec_module('ansible.windows.win_stat', 
           modargs={'path': str(fp)}
        )


    def _link_file_is_uncritical(self, link_stat):
        ## TODO: junctions should also be uncritical, or???
        ##if link_stat['islnk'] or link_stat['isjunction']:
        if link_stat['islnk']:
            return True

        if link_stat['hlnk_targets']:
            ## hard links are only uncritical if the queried path is 
            ## not the last/only hard link, as the tested field contains 
            ## all hard link paths except the queried one testing if it 
            ## is not empty is enough here
            return True

        return False


    def _handle_present_symbolic(self, result, link_stat, target_stat):
        def check_link():
            force = self.get_taskparam('force')
            overwrite = self.get_taskparam('overwrite') or force

            if not link_stat['exists']:
                return True

            if link_stat['islnk']:
                p1 = pathlib.PureWindowsPath(link_stat['lnk_source'])
                p2 = pathlib.PureWindowsPath(target_stat['path'])

                if p1 == p2:
                    ## link exists, is symbolic and matches defined 
                    ## target, noop / green case
                    display.v(
                       "[FS_LINK] :: link exists already, is symbolic"\
                       " and matches expected target --> noop/green"
                    )

                    return False

            if self._link_file_is_uncritical(link_stat):
                if overwrite:
                    return True

                raise AnsibleOptionsError(
                   "Given link path '{}' already exists on target"\
                   " system as an uncritical link type to another"\
                   " target, if overwriting is acceptable set"\
                   " optional parameter 'overwrite' to true: {}".format(
                      link_stat['path'], link_stat
                   )
                )

            if force:
                return True

            raise AnsibleOptionsError(
               "Given link path '{}' already exists on target system"\
               " as critical possible unique pointer to some content,"\
               " if overwriting is acceptable set optional parameter"\
               " 'force' to true, be aware that this a potential"\
               " dangerous operation with the possibility to remove"\
               " some content forever and irreversible: {}".format(
                  link_stat['path'], link_stat
               )
            )

        if not check_link():
            return  ## noop

        ## create symbolic link
        result['changed'] = True

        if link_stat['exists']:
            ## remove old link file first
            self._handle_absent(result, link_stat, from_present=True)

        ## create new link
        cmd = ['mklink']

        if target_stat['isdir']:
            cmd += ['/d']

        cmd += [
          '"' + link_stat['path'] + '"', '"' + target_stat['path'] + '"'
        ]

        ##
        ## note: there are more powershell-ly variants of creating 
        ##   symbolic links that using mklink (which only works with 
        ##   legacy cmd interpreter), but they seem to have all more 
        ##   caveats than good old mklink, see for example:
        ##
        ##      https://stackoverflow.com/q/894430
        ##
        self.exec_powershell_script(' '.join(cmd), cmd_exe=True)


    def _handle_present(self, result, link_stat):
        target_path = self.get_taskparam('target_path')

        if not target_path:
            raise AnsibleOptionsError(
              "When mode is 'present', 'target_path' parameter must be set"
            )

        link_type = self.get_taskparam('link_type')

        ## check if target path exists and what type it is (file, dir, ...)
        trgt_stat = self._query_win_filepath(target_path, 'target_path', 
          relpath_root=pathlib.PureWindowsPath(link_stat['path']).parent
        )

        trgt_stat = trgt_stat['stat']

        if not trgt_stat['exists']:
            raise AnsibleOptionsError(
               "Invalid target path param: path must exists on target"\
               " system, but given path '{}' does not".format(target_path)
            )

        getattr(self, '_handle_present_' + link_type)(
           result, link_stat, trgt_stat
        )


    def _handle_absent(self, result, link_stat, from_present=False):
        if not from_present:
            if not link_stat['exists']:
                display.vv(
                  "[FS_LINK] :: absenting a non existing link --> noop/green"
                )

                return

            if not self._link_file_is_uncritical(link_stat):
                if not self.get_taskparam('force'):
                    raise AnsibleOptionsError(
                       "Given link path '{}' is either not a link or the"\
                       " last existing hard link to a file / dir, so"\
                       " removing it might lead to irreversible data loss,"\
                       " if this is acceptable set 'force' parameter"\
                       " to true: {}".format(link_stat['path'], link_stat)
                    )

            result['changed'] = True

        ##
        ## note: win_file has no special handling for links builtin 
        ##   (like its linux counterpart), hence the reason for this 
        ##   module, this leaves on first sight the question open if 
        ##   on delete the link file is deleted, or the linked to 
        ##   target, experimenting confirms the first one, so yeah, 
        ##   we can simply call it here for handle the link deleting 
        ##   on remote system
        ##
        self.exec_module('ansible.windows.win_file', 
           modargs={'path': link_stat['path'], 'state': 'absent'}
        )


    def run_specific(self, result):
        link_path = self.get_taskparam('link_path')
        state = self.get_taskparam('state')

        ## check if something exists on link_path
        link_stat = self._query_win_filepath(link_path, 'link_path')
        display.vv(
           "[FS_LINK] :: queried link path stat: {}".format(link_stat)
        )

        link_stat = link_stat['stat']
        
        link_stat['path'] = link_stat.get('path', link_path)

        ## do state dependend operation
        getattr(self, '_handle_' + state)(result, link_stat)

        return result 

