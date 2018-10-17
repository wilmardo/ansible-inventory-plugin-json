# Copyright (c) 2018 Intermax Automation

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = '''
    name: eva_inventory
    plugin_type: inventory
    authors:
        - Wilmar den Ouden <w.denouden@intermax.nl>
    short_description: Intermax (EVA) inventory source
    description:
        - Fetch hosts from EVA by ID
    requirements:
      - whitelisting in configuration
      - python-requests library
    options:
        url:
            description: URL of EVA POST endpoint 
            env:
                - name: EVA_INVENTORY_URL
            required: True
            ini:
                - section: eva_inventory
                  key: url          
        token:
            description: Bearer token to authenticate with the EVA POST endpoint 
            env:
                - name: EVA_INVENTORY_TOKEN
            required: True
            ini:
                - section: eva_inventory
                  key: token
        parameters:
            description: id of which JSON to GET from EVA
            type: string
            default: ''
'''


from ansible.errors import AnsibleError, AnsibleParserError
from ansible.module_utils.six import iteritems
from ansible.module_utils._text import to_native
from ansible.plugins.inventory import BaseInventoryPlugin
from requests import get, ConnectionError, HTTPError, Timeout, TooManyRedirects
from os import environ


class InventoryModule(BaseInventoryPlugin):
    """Host inventory parser for Ansible using data from EVA"""

    # These options do not seem to be implemented yet, but kept for future compatibility
    INVENTORY_NAME = 'eva_inventory'
    INVENTORY_VERSION = 0.1
    INVENTORY_NEEDS_WHITELIST = True

    EVA_URL = ""
    EVA_TOKEN = ""

    def __init__(self):
        super(InventoryModule, self).__init__()
        self._hosts = set()
        self.disabled = False

    def parse(self, inventory, loader, client_id, cache=None):
        super(InventoryModule, self).parse(inventory, loader, client_id, cache=cache)

        try:
            self.EVA_URL = os.environ('EVA_URL')
            self.EVA_TOKEN = os.environ('EVA_TOKEN')
            if self.EVA_URL is None:
                raise ValueError('No url value specified')
            if self.EVA_TOKEN is None:
                raise ValueError('No token value specified')
        except (KeyError, ValueError) as e:
            # FIXME: _display not yet implemented for InventoryModule like CallbackModule has
            # self._display.warning("Missing option for EVA callback plugin: %s" % to_native(e))
            self.disabled = True

            if deployment_id:
                response = self._get_json()
                json_response = self.loader.load(response)
                self._parse_to_inventory(json_response)
            else:
                self.disabled = True
                # FIXME: Fix proper exception
                raise Exception

        except Exception as e:
            raise AnsibleParserError(to_native(e))

    def verify_file(self, path):
        return True

    def _get_json(self):
        headers = {
            'Authorization': 'Bearer ' + self.EVA_TOKEN,
            'Accept': 'application/json'
        }
        try:
            response = get(self.EVA_URL, headers=headers)
            response.raise_for_status()
            return response.content
        except (ConnectionError, HTTPError, Timeout, TooManyRedirects) as e:
            raise AnsibleError(to_native(e))

    def _parse_to_inventory(self, data):
        # Repurpose https://github.com/ansible/ansible/blob/devel/lib/ansible/plugins/inventory/script.py

        group = None
        data_from_meta = None

        # A "_meta" subelement may contain a variable "hostvars" which contains a hash for each host
        # if this "hostvars" exists at all then do not call --host for each # host.
        # This is for efficiency and scripts should still return data
        # if called with --host for backwards compat with 1.2 and earlier.
        for (group, gdata) in data.items():
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

            self._populate_host_vars([host], got)  # 2.5 renamed to _populate_host_vars

    def _parse_group(self, group, data):
        # Repurpose https://github.com/ansible/ansible/blob/devel/lib/ansible/plugins/inventory/script.py'

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
