# Copyright (c) Trainline Limited, 2016-2017. All rights reserved. See LICENSE.txt in the project root for license information.

import unittest
from jsonschema import ValidationError
from mock import Mock, patch
from agent.deployment_stages.common import DeploymentError
from agent.deployment_stages.sensu_healthchecks import RegisterSensuHealthChecks

class MockLogger(object):
    def __init__(self):
        self.info = Mock()
        self.error = Mock()
        self.debug = Mock()
        self.warning = Mock()

class MockService(object):
    slice = None

    def set_slice(self, slice):
        self.slice = slice

class MockDeployment(object):
    def __init__(self):
        self.logger = MockLogger()
        self.archive_dir = ''
	self.platform = 'windows'
        self.instance_tags = {
            'Environment': 'local',
            'Role': 'role',
            'OwningCluster': 'cluster'
        }
        self.sensu = {
            'healthcheck_search_paths': ['sensu_plugins_path']
        }
        self.service = MockService()

class TestRegisterSensuHealthChecks(unittest.TestCase):
    def setUp(self):
        self.deployment = MockDeployment()

    def test_validate_missing_name_property(self):
        check = {}
        with self.assertRaisesRegexp(ValidationError, "'name' is a required property"):
            RegisterSensuHealthChecks.validate_check_properties('check_id', check)

    def test_validate_missing_interval_property(self):
        check = {
            'name': 'Missing-interval'
        }
        with self.assertRaisesRegexp(ValidationError, "'interval' is a required property"):
            RegisterSensuHealthChecks.validate_check_properties('check_id', check)

    def test_validate_missing_script_property(self):
        check = {
            'name': 'Missing-interval',
            'interval': 10
        }
        with self.assertRaisesRegexp(DeploymentError, 'you need at least one of'):
            RegisterSensuHealthChecks.validate_check_properties('check_id', check)

    def test_validate_both_scripts_properties_provided(self):
        check = {
            'name': 'missing-interval',
            'interval': 10,
            'local_script': 'a',
            'server_script': 'b',
        }
        with self.assertRaisesRegexp(DeploymentError, "you can use either 'local_script' or 'server_script'"):
            RegisterSensuHealthChecks.validate_check_properties('check_id', check)

    def test_validate_name_does_not_match_regexp(self):
        check = {
            'name': 'missing http',
            'local_script': 'a',
            'interval': 10,
        }
        with self.assertRaisesRegexp(DeploymentError, 'match required Sensu name expression'):
            RegisterSensuHealthChecks.validate_check_properties('check_id', check)

    def test_validate_integer_type_properties(self):
        check = {
            'name': 'missing-http',
            'local_script': 'a',
            'team': 'some_team'
        }
        property_names = ['interval', 'realert_every', 'timeout', 'occurrences', 'refresh']
        last_property_name = None
        for property_name in property_names:
            if last_property_name is not None:
                check[property_name] = 10
            check[property_name] = '10s'
            last_property_name = property_name
            with self.assertRaisesRegexp(ValidationError, "'{0}' is not of type 'number'".format(check[property_name])):
                RegisterSensuHealthChecks.validate_check_properties('check_id', check)

    def test_validate_override_notification_email_property(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'foo.py',
            'override_notification_email': ['foo', 'bar'],
            'interval': 10
        }
        with self.assertRaisesRegexp(ValidationError, "'foo' does not match"):
            RegisterSensuHealthChecks.validate_check_properties('check_id', check)

    def test_validate_all_ids_unique(self):
        checks = {
            'check_1': {
                'name': 'missing-http-1',
                'local_script': 'script.sh',
                'interval': 10
            },
            'cheCK_1': {
                'name': 'missing-http-2',
                'local_script': 'script.sh',
                'interval': 10
            }
        }
        with self.assertRaisesRegexp(DeploymentError, 'Sensu check definitions require unique ids'):
            RegisterSensuHealthChecks.validate_unique_ids(checks)

    def test_validate_all_names_unique(self):
        checks = {
            'check_1': {
                'name': 'missing-http',
                'local_script': 'script.sh',
                'interval': 10
            },
            'check_2': {
                'name': 'missing-http',
                'local_script': 'script.sh',
                'interval': 10
            }
        }
        with self.assertRaisesRegexp(DeploymentError, 'Sensu check definitions require unique names'):
            RegisterSensuHealthChecks.validate_unique_names(checks)

    def test_validate_missing_local_script(self):
        def file_exists(path):
            return False
        patcher = patch('os.path.exists')
        mock = patcher.start()
        mock.side_effect = file_exists

        check = {
            'name': 'missing-http',
            'local_script': 'script.sh',
            'interval': 10,
            'team': 'some_team'
        }
        with self.assertRaisesRegexp(DeploymentError, "Couldn't find Sensu check script"):
            RegisterSensuHealthChecks.validate_check_script(check, '/some/path', self.deployment)

    def test_validate_missing_sensu_plugin_script(self):
        def file_exists(path):
            return False
        patcher = patch('os.path.exists')
        mock = patcher.start()
        mock.side_effect = file_exists

        check = {
            'name': 'missing-http',
            'server_script': 'script.sh',
            'interval': 10,
            'team': 'some_team'
        }
        with self.assertRaisesRegexp(DeploymentError, "Couldn't find Sensu plugin script"):
            RegisterSensuHealthChecks.validate_check_script(check, None, self.deployment)

    def test_warning_deprecated_properties(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'foo.py',
            'notification_email': ['foo@bar.com', 'bar@biz.uk'],
            'interval': 10
        }
        definition = RegisterSensuHealthChecks.generate_check_definition(check, 'test_path', self.deployment)
        self.deployment.logger.warning.assert_called_with("'notification_email' property is deprecated, please use 'override_notification_email' instead")
        self.assertEqual(definition['checks']['sensu-check1']['notification_email'], 'foo@bar.com,bar@biz.uk')

    def test_generate_check_definition_with_valid_team_property(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'foo.py',
            'interval': 10
        }
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, 'test_path', self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['team'], None)
        check['override_notification_settings'] = 'dietcode'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, 'test_path', self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['team'], 'dietcode')

    def test_generate_check_definition_with_valid_list_of_emails_and_slack_channels(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'fuj.py',
            'override_notification_email': ['email1@ble.pl', 'email2@ble.pl'],
            'override_chat_channel': ['channel1', 'channel2'],
            'interval': 10
        }
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, 'test_path', self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['notification_email'], 'email1@ble.pl,email2@ble.pl')
        self.assertEqual(check_definition['checks']['sensu-check1']['slack_channel'], 'channel1,channel2')

    def test_generate_check_definition_with_default_values(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'foo.py',
            'interval': 10
        }
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, 'test_path', self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['aggregate'], False)
        self.assertEqual(check_definition['checks']['sensu-check1']['alert_after'], 600)
        self.assertEqual(check_definition['checks']['sensu-check1']['handlers'], ['default'])
        self.assertEqual(check_definition['checks']['sensu-check1']['notification_email'], 'undef')
        self.assertEqual(check_definition['checks']['sensu-check1']['occurrences'], 5)
        self.assertEqual(check_definition['checks']['sensu-check1']['page'], False)
        self.assertEqual(check_definition['checks']['sensu-check1']['project'], False)
        self.assertEqual(check_definition['checks']['sensu-check1']['realert_every'], 30)
        self.assertEqual(check_definition['checks']['sensu-check1']['slack_channel'], 'undef')
        self.assertEqual(check_definition['checks']['sensu-check1']['standalone'], True)
        self.assertEqual(check_definition['checks']['sensu-check1']['subscribers'], ['sensu-base'])
        self.assertEqual(check_definition['checks']['sensu-check1']['ticket'], False)
        self.assertEqual(check_definition['checks']['sensu-check1']['timeout'], 120)

    def test_generate_check_definition_with_instance_tags(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'foo.py',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, 'test_path', self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['ttl_environment'], self.deployment.instance_tags['Environment'])
        self.assertEqual(check_definition['checks']['sensu-check1']['ttl_owningcluster'], self.deployment.instance_tags['OwningCluster'])
        self.assertEqual(check_definition['checks']['sensu-check1']['ttl_role'], self.deployment.instance_tags['Role'])

    def test_generate_linux_check_definition_with_command_and_no_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'foo.sh',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'foo.sh')

    def test_generate_linux_check_definition_with_command_and_none_slice_and_no_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'foo.sh',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        self.deployment.service.slice = 'none'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'foo.sh')
    
    def test_generate_linux_local_check_definition_with_command_and_slice_and_no_arguments(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'foo.sh',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        self.deployment.service.slice = 'green'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['local_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'foo.sh green')
    
    def test_generate_linux_server_check_definition_with_command_and_slice_and_no_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'foo.sh',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        self.deployment.service.slice = 'green'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'foo.sh')
    
    def test_generate_linux_check_definition_with_command_and_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'foo.sh',
            'script_arguments': '-o service_name',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'foo.sh -o service_name')

    def test_generate_linux_local_check_definition_with_command_and_slice_and_arguments(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'foo.sh',
            'script_arguments': '-o service_name',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        self.deployment.service.slice = 'blue'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['local_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'foo.sh -o service_name blue')
    
    def test_generate_linux_server_check_definition_with_command_and_slice_and_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'foo.sh',
            'script_arguments': '-o service_name',
            'interval': 10
        }
        self.deployment.platform = 'linux'
        self.deployment.service.slice = 'blue'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'foo.sh -o service_name')
    
    def test_generate_windows_check_definition_with_command_and_no_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'foo.ps1',
            'interval': 10
        }
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'powershell.exe -NonInteractive -NoProfile -ExecutionPolicy RemoteSigned -file foo.ps1')

    def test_generate_windows_check_definition_with_command_and_none_slice_and_no_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'foo.ps1',
            'interval': 10
        }
        self.deployment.service.slice = 'none'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'powershell.exe -NonInteractive -NoProfile -ExecutionPolicy RemoteSigned -file foo.ps1')
    
    def test_generate_windows_check_definition_with_command_and_arguments(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'C:\\Programs Files (x86)\\Sensu\\plugins\\check-windows-service.ps1',
            'script_arguments': '-ServiceName service_name',
            'interval': 10
        }
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'powershell.exe -NonInteractive -NoProfile -ExecutionPolicy RemoteSigned -file C:\\Programs Files (x86)\\Sensu\\plugins\\check-windows-service.ps1 -ServiceName service_name')
    
    def test_generate_local_check_definition_with_command_and_arguments_and_slice(self):
        check = {
            'name': 'sensu-check1',
            'local_script': 'C:\\Programs Files (x86)\\Sensu\\plugins\\check-windows-service.ps1',
            'script_arguments': '-ServiceName service_name',
            'interval': 10
        }
        self.deployment.service.slice = 'green'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['local_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'powershell.exe -NonInteractive -NoProfile -ExecutionPolicy RemoteSigned -file C:\\Programs Files (x86)\\Sensu\\plugins\\check-windows-service.ps1 -ServiceName service_name green')
    
    def test_generate_server_check_definition_with_command_and_arguments_and_slice(self):
        check = {
            'name': 'sensu-check1',
            'server_script': 'C:\\Programs Files (x86)\\Sensu\\plugins\\check-windows-service.ps1',
            'script_arguments': '-ServiceName service_name',
            'interval': 10
        }
        self.deployment.service.slice = 'green'
        check_definition = RegisterSensuHealthChecks.generate_check_definition(check, check['server_script'], self.deployment)
        self.assertEqual(check_definition['checks']['sensu-check1']['command'], 'powershell.exe -NonInteractive -NoProfile -ExecutionPolicy RemoteSigned -file C:\\Programs Files (x86)\\Sensu\\plugins\\check-windows-service.ps1 -ServiceName service_name')
