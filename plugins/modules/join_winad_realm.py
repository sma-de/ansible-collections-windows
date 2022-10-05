#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2021, SMA Solar Technology
# BSD 3-Clause Licence (see LICENSE or https://spdx.org/licenses/BSD-3-Clause.html)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


# TODO: support joining per kerberos ticket
DOCUMENTATION = r'''
---
module: join_winad_realm

short_description: Joins a linux machine to windows activery directory

version_added: "1.0.0"

description: >-
  This module joins linux machine to an active directory. It is build
  around / relies on the realmd service which must be installed
  beforehand on the machine.

options:
    user:
      description: >-
        AD user (name) used as credential. So the chosen user obviously
        must have sufficient rights to join machines into the specified AD.
      type: str
      required: true
    password:
      description: >-
        Password for given I(user).
      type: str
      required: true
    domain:
      description: >-
        Name of the domain which should be joined.
      type: str
      required: true
    ou:
      description: >-
        LDAP / AD organisational unit attribute.
      type: str
      required: false
    state:
      description: >-
        Present or absent like always.
      type: str
      required: false
      default: 'present'

author:
    - Mirko Wilhelmi (@yourGitHubHandle)
'''

# TODO: github handle
EXAMPLES = r'''
- name: join ad realm
  smabot.windows.join_winad_realm:
    user: adusr
    password: user_pw
    domain: example.com

- name: join ad realm with ou
  smabot.windows.join_winad_realm:
    user: adusr
    password: user_pw
    domain: example.com
    ou: OU=Server,OU=Eurpoe,OU=Sites,DC=example,DC=com

'''

RETURN = r'''
ansible_facts:
  description: TODO: fix this
  returned: always
  type: dict
  contains:
    java:
      description: Java facts about the system.
      type: dict
      returned: when one or more JVM installations can be successfully detected on target system
      contains:
        installations:
          description: One or more JVM(s) found on target system.
          type: list
          elements: dict
          sample: 
          - - active: false
              binary: /opt/java/openjdk/bin/java
              homedir: /opt/java/openjdk
              type: UNKOWN
              version: 1.8.0_292
              build: 1.8.0_292-b10
            - active: true
              binary: /usr/local/share/java/bin/java
              homedir: /usr/local/share/java
              type: AdoptOpenJDK
              version: 1.7.0_142
              build: 1.7.0_142-b13
        active:
          description:
          - Facts about the "active" JVM on remote.
          - This is a direct reference to one of JVMs in I(installations).
          type: dict
          sample: 
            active: true
            binary: /usr/local/share/java/bin/java
            homedir: /usr/local/share/java
            type: AdoptOpenJDK
            version: 1.7.0_142
            build: 1.7.0_142-b13
'''

##import abc
##import collections
##import os
##import re

from ansible.module_utils.basic import AnsibleModule



class RealmJoiner(AnsibleModule):

    def discover_domain(self, result, domain):
        # note: note 100% it is necessary but you can often find the tip
        #   on the interwebs that it is better to use all uppercase
        #   writing for domain for specific commandos
        dom_upper  = domain.upper()

        # check that domain is discoverable
        rc, stdout, stderr = self.run_command(
          ['realm', 'discover', dom_upper]
        )

        if rc != 0:
            self.fail_json(
               "Trying to discover given AD domain"\
               " failed with rc '{}': {}".format(rc, stderr),
               **result
            )

        if not stdout:
            self.fail_json(
               "Given AD could not be discovered, make sure the domain"\
               " string is spelled correctly and that all necessary"\
               " network ports are accessable",
               **result
            )

        #
        # parse domain discover output, first line is expected to just
        # contain the domain name while all following lines should be
        # kv mappings for various attributes of the domain like in
        # the following example:
        #
        # realm discover FOO.BAR
        # sma.de
        #   type: kerberos
        #   realm-name: FOO.BAR
        #   domain-name: foo.bar
        #   configured: kerberos-member
        #   server-software: active-directory
        #   client-software: sssd
        #   required-package: sssd-tools
        #   required-package: sssd
        #   required-package: libnss-sss
        #   required-package: libpam-sss
        #   required-package: adcli
        #   required-package: samba-common-bin
        #   login-formats: %U@foo.bar
        #   login-policy: allow-realm-logins
        #
        stdout = stdout.strip().split('\n')
        stdout = stdout[1:]

        res = {}

        i = 1
        for x in stdout:
            x = x.strip()

            try:
                k, v = x.split(':')
            except ValueError:
                self.fail_json(
                   "Unexpected bad AD domain discover output line[{}] '{}',"\
                   " only expect key-value lines in the format"\
                   " 'key: value':\n{}".format(i, x, '\n'.join(stdout)),
                   **result
                )

            res[k.strip()] = v.strip()
            i += 1

        return res


    def check_is_joined(self, result, domain):
        # check if we are already joined to given ad
        rc, stdout, stderr = self.run_command(
          ['realm', 'list', '--name-only']
        )

        if rc != 0:
            self.fail_json(
               "Checking if we are already joined to given AD domain"\
               " failed with rc '{}': {}".format(rc, stderr),
               **result
            )

        if not stdout:
            return False

        # each line of output should be a name of a
        # domain this machine is joined to
        for x in stdout.split('\n'):
            if x.lower() == domain:
                return True

        return False


    def get_mod_retval(self, result, domain, discover=True):
        tmp = {}

        if discover:
            tmp[domain] = self.discover_domain(result, domain)

        return {'domains': tmp}


    def join_or_leave(self, command, result, domain):
        # note: note 100% it is necessary but you can often find the tip
        #   on the interwebs that it is better to use all uppercase
        #   writing for domain for specific commandos
        dom_upper  = domain.upper()

        # TODO: support other ways of giving join credentials (e.g. kerbereos ticket)
        # TODO: support other optional join params
        kwargs = {}
        args = ['realm', command, '-v']

        user = self.params['user']

        if user:
            args += ['--user', user]

            # note: unfortunately this seems not to work for some reason
            ##kwargs['prompt_regex'] = r'(?i)password\s+.*{}\s*:'.format(user)

        if command == 'join':
            # handle join specific args
            ou = self.params['ou']

            if ou:
                args += ['--computer-ou', ou]
        else:
            # handle leave specific args
            remove_machine = True # TODO: make this a module option??

            if remove_machine:
                args += ['--remove']

        args.append(dom_upper)

        pw = self.params['password']

        if pw:
            kwargs['data'] = pw
            kwargs['binary_data'] = True

        rc, stdout, stderr = self.run_command(
          args, **kwargs
        )

        if rc != 0:
            self.fail_json(
               "Trying to {} given AD domain"\
               " failed with rc '{}': {}".format(command, rc, stderr),
               **result
            )

        # assure that join/leave has worked
        post_joined = self.check_is_joined(result, domain)

        if command == 'join':
            if not post_joined:
                self.fail_json(
                   "Post join membership check failed for given AD domain,"\
                   " seemingly something went wrong during join process"
                   **result
                )

        else:
            if post_joined:
                self.fail_json(
                   "Still being part of given AD domain post leave command,"\
                   " seemingly something went wrong during leave process"
                   **result
                )


    def handle_absent(self, result, domain):
        if not self.check_is_joined(result, domain):
            ## state absent and machine is not joined => noop
            return self.get_mod_retval(result, domain, discover=False)

        result['changed'] = True

        self.join_or_leave('leave', result, domain)
        return self.get_mod_retval(result, domain, discover=False)


    def handle_present(self, result, domain):
        if self.check_is_joined(result, domain):
            ## state present and machine is already joined => noop
            return self.get_mod_retval(result, domain)

        result['changed'] = True

        # check that domain is discoverable
        self.discover_domain(result, domain)

        # join to ad
        self.join_or_leave('join', result, domain)
        return self.get_mod_retval(result, domain)


    def run(self, result):
        state = self.params['state']
        dom_normed = self.params['domain'].lower()

        state_fn = getattr(self, 'handle_' + state, None)

        if not state_fn:
            self.fail_json(
               "Given state '{}' is not supported".format(state),
               **result
            )

        return state_fn(result, dom_normed)



def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
      user=dict(
        type='str',
        required=True,
      ),
      password=dict(
        type='str',
        required=True,
        no_log=True,
      ),
      domain=dict(
        type='str',
        required=True,
      ),
      ou=dict(
        type='str',
      ),
      state=dict(
        type='str',
        default='present',
        choices=['present', 'absent'],
      ),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
      changed=False,
      ansible_facts=dict(),
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = RealmJoiner(
      argument_spec=module_args,
      ##supports_check_mode=True #TODO: check mode
      supports_check_mode=False
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    result['ansible_facts'] = module.run(result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)



def main():
    run_module()



if __name__ == '__main__':
    main()

