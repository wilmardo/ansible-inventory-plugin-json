# Copyright (c) 2018 Wilmar den Ouden

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = '''
    name: JSON
    plugin_type: inventory
    authors:
        - Wilmar den Ouden <info@wilmardenouden.nl>
    short_description: Remote JSON inventory source
    description:
        - Fetch hosts from JSON url's
    options:
        hosts:
            description: url's of JSON to get
            type: list
            default: []
'''

try:
    from urllib.request import urlopen
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import urlopen, URLError, HTTPError

import json

from ansible.errors import AnsibleError, AnsibleParserError
from ansible.module_utils.six import iteritems
from ansible.module_utils._text import to_native
from ansible.plugins.inventory import BaseInventoryPlugin
from ansible.inventory.manager import InventoryData


class InventoryModule(BaseInventoryPlugin):
    """ Host inventory parser for Ansible using data from remote JSON """

    NAME = 'JSON'

    def __init__(self):

        super(InventoryModule, self).__init__()

        self._hosts = set()

    def verify_file(self, path):
        return True

    # TODO: Check if parsing multiple json after request and then _parse_to_inventory is faster
    def parse(self, inventory, loader, url_list, cache=None):
        path = 'inventory/'
        super(InventoryModule, self).parse(inventory, loader, path, cache=cache)

        try:
            for u in url_list.split(','):
                u = u.strip()
                if u:
                    response = self._get_json(u)
                    self._parse_to_inventory(self.loader.load(response))

        except Exception as e:
            raise AnsibleParserError(to_native(e))

    def _get_json(self, url):
        try:
            return urlopen(url).read()
        except HTTPError as e:
            raise AnsibleError('The server (%s) couldn\'t fulfill the request, code: %s' % (url, e.code))
        except URLError as e:
            raise AnsibleError('The server (%s) couldn\'t be reached, reason: %s' % (url, e.reason))

    def _parse_to_inventory(self, rjson):
        '''Repurpose https://github.com/ansible/ansible/blob/devel/lib/ansible/plugins/inventory/script.py'''
        group = None
        data_from_meta = None

        # A "_meta" subelement may contain a variable "hostvars" which contains a hash for each host
        # if this "hostvars" exists at all then do not call --host for each # host.
        # This is for efficiency and scripts should still return data
        # if called with --host for backwards compat with 1.2 and earlier.
        for (group, gdata) in rjson.items():
            if group == '_meta':
                if 'hostvars' in gdata:
                    data_from_meta = gdata['hostvars']
            else:
                self._parse_group(group, gdata)

        for host in self._hosts:
            got = {}
            if data_from_meta is not None:
                try:
                    got = data_from_meta.get(host, {})
                except AttributeError as e:
                    raise AnsibleError("Improperly formatted host information for %s: %s" % (host, to_native(e)))

            self.populate_host_vars([host], got)  # 2.5 renamed to _populate_host_vars

    def _parse_group(self, group, data):
        '''Repurpose https://github.com/ansible/ansible/blob/devel/lib/ansible/plugins/inventory/script.py'''

        self.inventory.add_group(group)

        if not isinstance(data, dict):
            data = {'hosts': data}
        # is not those subkeys, then simplified syntax, host with vars
        elif not any(k in data for k in ('hosts', 'vars', 'children')):
            data = {'hosts': [group], 'vars': data}

        if 'hosts' in data:
            if not isinstance(data['hosts'], list):
                raise AnsibleError("You defined a group '%s' with bad data for the host list:\n %s" % (group, data))

            for hostname in data['hosts']:
                self._hosts.add(hostname)
                self.inventory.add_host(hostname, group)

        if 'vars' in data:
            if not isinstance(data['vars'], dict):
                raise AnsibleError("You defined a group '%s' with bad data for variables:\n %s" % (group, data))

            for k, v in iteritems(data['vars']):
                self.inventory.set_variable(group, k, v)

        if group != '_meta' and isinstance(data, dict) and 'children' in data:
            for child_name in data['children']:
                self.inventory.add_group(child_name)
                self.inventory.add_child(group, child_name)
