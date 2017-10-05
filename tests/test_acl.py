# Copyright 2017 rpaas authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

import consul
import copy
import mock
import os
import unittest
from rpaas.acl import (AclManager, AclApiError)
from rpaas import consul_manager


class AclManagerTestCase(unittest.TestCase):

    def setUp(self):
        self.master_token = "rpaas-test"
        os.environ.setdefault("RPAAS_SERVICE_NAME", "rpaas-acl")
        os.environ.setdefault("CONSUL_HOST", "127.0.0.1")
        os.environ.setdefault("CONSUL_TOKEN", self.master_token)
        self.consul = consul.Consul(token=self.master_token)
        self.consul.kv.delete("rpaas-acl", recurse=True)
        self.storage = consul_manager.ConsulManager(os.environ)
        self.config = {
            "ACL_API_HOST": "http://aclapihost",
            "ACL_API_USER": "acluser",
            "ACL_API_PASSWORD": "aclpassword"
        }

    def tearDown(self):
        del os.environ["RPAAS_SERVICE_NAME"]

    @mock.patch("rpaas.acl.requests")
    def test_add_acl_without_networkapi(self, requests):
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"jobs": "3", "result": "success"}'

        requests.request.return_value = response
        acl_manager = AclManager(self.config, self.storage)
        acl_manager.acl_auth_basic = "{}/{}".format(acl_manager.acl_auth_basic.username,
                                                    acl_manager.acl_auth_basic.password)
        acl_manager.add_acl("myrpaas", "10.0.0.1", "192.168.0.1/24")
        expected_data = {'kind': 'object#acl',
                         'rules': [{'l4-options': {'dest-port-op': 'range',
                                                   'dest-port-start': '30000',
                                                   'dest-port-end': '61000'},
                                    'protocol': 'tcp',
                                    'description': 'permit 10.0.0.1/32 rpaas access for rpaas instance myrpaas',
                                    'destination': '192.168.0.1/24',
                                    'source': '10.0.0.1/32',
                                    'action': 'permit'}]}
        requests.request.assert_called_with("put", 'http://aclapihost/api/ipv4/acl/10.0.0.1/32',
                                            auth="acluser/aclpassword", json=expected_data, timeout=30)
        data = self.storage.find_acl_network("myrpaas")
        expected_storage = [{'destination': ['192.168.0.1/24'], 'source': '10.0.0.1/32'}]
        self.assertEqual(data, expected_storage)

    @mock.patch("rpaas.acl.requests")
    def test_add_acl_using_networkapi(self, requests):
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"jobs": "3", "result": "success"}'
        requests.request.return_value = response
        config = copy.deepcopy(self.config)
        config.update({'NETWORK_API_URL': 'https://networkapi'})

        acl_manager = AclManager(config, self.storage)
        acl_manager.ip_client = mock.Mock()
        acl_manager.ip_client.get_ipv4_or_ipv6.side_effect = [{'ips': {'networkipv4': '153806'}},
                                                              {'ips': {'networkipv4': '153806'}},
                                                              {'ips': {'networkipv4': '153806'}},
                                                              {'ips': {'networkipv4': '153806'}}]
        acl_manager.network_client = mock.Mock()
        acl_manager.network_client.get_network_ipv4.side_effect = [{'network': {'block': '27'}},
                                                                   {'network': {'block': '24'}},
                                                                   {'network': {'block': '27'}},
                                                                   {'network': {'block': '24'}}
                                                                   ]
        acl_manager.acl_auth_basic = "{}/{}".format(acl_manager.acl_auth_basic.username,
                                                    acl_manager.acl_auth_basic.password)
        acl_manager.add_acl("myrpaas", "10.0.0.1", "192.168.0.1")
        acl_manager.add_acl("myrpaas", "10.0.0.1", "192.168.0.2")
        expected_data = {'kind': 'object#acl',
                         'rules': [{'l4-options': {'dest-port-op': 'range',
                                                   'dest-port-start': '30000',
                                                   'dest-port-end': '61000'},
                                    'protocol': 'tcp',
                                    'description': 'permit 10.0.0.1/32 rpaas access for rpaas instance myrpaas',
                                    'destination': '192.168.0.0/24',
                                    'source': '10.0.0.1/32',
                                    'action': 'permit'}]}
        requests.request.assert_called_once_with("put", 'http://aclapihost/api/ipv4/acl/10.0.0.0/27',
                                                 auth="acluser/aclpassword", json=expected_data, timeout=30)
        data = self.storage.find_acl_network("myrpaas")
        expected_storage = [{'destination': ['192.168.0.0/24'], 'source': '10.0.0.1/32'}]
        self.assertEqual(data, expected_storage)

    @mock.patch("rpaas.acl.requests")
    def test_add_acl_invalid_job_returned(self, requests):
        response = mock.Mock()
        response.status_code = 200
        response.text = "invalid json"

        requests.request.return_value = response
        acl_manager = AclManager(self.config, self.storage)
        acl_manager.acl_auth_basic = "{}/{}".format(acl_manager.acl_auth_basic.username,
                                                    acl_manager.acl_auth_basic.password)
        with self.assertRaises(AclApiError) as cm:
            acl_manager.add_acl("myrpaas", "10.0.0.1", "192.168.0.1/24")
        self.assertEqual(cm.exception.message, "no valid json returned")

    @mock.patch("rpaas.acl.requests")
    def test_remove_acl_successfully(self, requests):
        response_texts = ['''
{
    "envs": [{
        "environment": "123",
        "kind": "default#acl",
        "rules": [{
            "id": "478",
            "action": "permit",
            "protocol": "ip",
            "source": "0.0.0.0/0",
            "destination": "10.70.1.80/32"
        }]
    }, {
        "kind": "default#acl",
        "environment": "139",
        "rules": [{
            "id": "68",
            "source": "0.0.0.0/0",
            "destination": "10.70.1.80/32"
        }],
        "vlans": [{
            "kind": "object#acl",
            "environment": "139",
            "num_vlan": 250,
            "rules": [{
                "id": "854",
                "source": "10.0.0.1/32",
                "destination": "192.168.0.0/24"
            }]

        }, {
            "kind": "object#acl",
            "environment": "139",
            "num_vlan": 165,
            "rules": [{
                "id": "1221",
               "source": "10.0.0.1/32",
                "destination": "192.168.0.0/24"
            }]
        }]
    }]
}
''', '{"job":4, "result":"success"}', '{"job":5, "result":"success"}', '''
{
    "envs": [{
        "environment": "123",
        "vlans": [{
            "kind": "object#acl",
            "environment": "139",
            "num_vlan": 250,
            "rules": [{
                "id": "854",
                "source": "10.0.0.1/32",
                "destination": "192.168.1.0/24"
            }]
        }]
    }]
}
''', '{"job":6, "result":"success"}']
        response_texts.reverse()
        response_side_effects = []
        for _ in range(5):
            response = mock.Mock()
            response.status_code = 200
            response.text = response_texts.pop()
            response_side_effects.append(response)
        self.storage.store_acl_network("myrpaas", "10.0.0.1/32", "192.168.0.0/24")
        self.storage.store_acl_network("myrpaas", "10.0.0.1/32", "192.168.1.0/24")
        self.storage.store_acl_network("myrpaas", "10.0.1.2/32", "192.168.1.0/24")
        requests.request.side_effect = response_side_effects
        acl_manager = AclManager(self.config, self.storage)
        acl_manager.acl_auth_basic = "{}/{}".format(acl_manager.acl_auth_basic.username,
                                                    acl_manager.acl_auth_basic.password)
        acl_manager.remove_acl("myrpaas", "10.0.0.1")
        reqs = [mock.call('post', 'http://aclapihost/api/ipv4/acl/search', auth='acluser/aclpassword',
                          json={'l4-options': {'dest-port-op': 'range',
                                               'dest-port-start': '30000',
                                               'dest-port-end': '61000'},
                                'protocol': 'tcp',
                                'description': 'permit 10.0.0.1/32 rpaas access for rpaas instance myrpaas',
                                'destination': '192.168.0.0/24',
                                'source': '10.0.0.1/32',
                                'action': 'permit'}, timeout=30),
                mock.call('delete', 'http://aclapihost/api/ipv4/acl/139/250/854', auth='acluser/aclpassword',
                          timeout=30),
                mock.call('delete', 'http://aclapihost/api/ipv4/acl/139/165/1221', auth='acluser/aclpassword',
                          timeout=30),
                mock.call('post', 'http://aclapihost/api/ipv4/acl/search', auth='acluser/aclpassword',
                          json={'l4-options': {'dest-port-op': 'range',
                                               'dest-port-start': '30000',
                                               'dest-port-end': '61000'},
                                'protocol': 'tcp',
                                'description': 'permit 10.0.0.1/32 rpaas access for rpaas instance myrpaas',
                                'destination': '192.168.1.0/24',
                                'source': '10.0.0.1/32',
                                'action': 'permit'}, timeout=30),
                mock.call('delete', 'http://aclapihost/api/ipv4/acl/139/250/854', auth='acluser/aclpassword',
                          timeout=30)
                ]
        requests.request.assert_has_calls(reqs)
        acls = self.storage.find_acl_network("myrpaas")
        expected_acls = [{'source': '10.0.1.2/32', 'destination': ['192.168.1.0/24']}]
        self.assertEqual(expected_acls, acls)

    @mock.patch("rpaas.acl.requests")
    def test_remove_acl_failure(self, requests):
        response_texts = ['''
        {
            "envs": [{
                "environment": "123",
                "vlans": [{
                    "kind": "object#acl",
                    "environment": "139",
                    "num_vlan": 250,
                    "rules": [{
                        "id": "854",
                        "source": "10.0.0.1/32",
                        "destination": "192.168.1.0/24"
                    }]
                }]
            }]
        }
        ''', '{"result":"failure"}']
        response_texts.reverse()
        response_side_effects = []
        for _ in range(2):
            response = mock.Mock()
            response.status_code = 200
            response.text = response_texts.pop()
            response_side_effects.append(response)
        self.storage.store_acl_network("myrpaas", "10.0.0.1/32", "192.168.1.0/24")
        requests.request.side_effect = response_side_effects
        acl_manager = AclManager(self.config, self.storage)
        acl_manager.acl_auth_basic = "{}/{}".format(acl_manager.acl_auth_basic.username,
                                                    acl_manager.acl_auth_basic.password)

        with self.assertRaises(AclApiError) as cm:
            acl_manager.remove_acl("myrpaas", "10.0.0.1")
        self.assertEqual(cm.exception.message, "invalid response: failure")
        acls = self.storage.find_acl_network("myrpaas")
        expected_acls = [{'source': '10.0.0.1/32', 'destination': ['192.168.1.0/24']}]
        self.assertEqual(expected_acls, acls)
