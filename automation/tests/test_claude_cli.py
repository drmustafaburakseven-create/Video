import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from automation import claude_cli as cli
from automation.state import PipelineError


def result(value, code=0):
    return Mock(stdout=json.dumps(value), stderr='PRIVATE-ERROR', returncode=code)


class ClaudeSubscriptionTests(unittest.TestCase):
    def test_api_billing_is_removed_but_subscription_proxy_and_ca_survive(self):
        env = {'ANTHROPIC_API_KEY': 'must-not-use', 'ANTHROPIC_BASE_URL': 'must-not-use',
               'CLAUDE_CODE_USE_VERTEX': '1', 'CLAUDE_CODE_SKIP_BEDROCK_AUTH': '1',
               'AWS_BEARER_TOKEN_BEDROCK': 'must-not-use',
               'CLAUDE_CODE_OAUTH_TOKEN': 'keep-private', 'CLAUDE_CONFIG_DIR': '/safe/auth',
               'ANTHROPIC_CONFIG_DIR': '/safe/auth2', 'HTTPS_PROXY': 'keep-proxy',
               'SSL_CERT_FILE': '/safe/ca'}
        clean = cli.subscription_environment(env)
        self.assertEqual(set(clean), {'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CONFIG_DIR',
                                     'ANTHROPIC_CONFIG_DIR', 'HTTPS_PROXY', 'SSL_CERT_FILE'})
        self.assertIn('ANTHROPIC_API_KEY', env)

    def test_auth_status_does_not_leak_identity_or_tokens(self):
        with patch.object(cli, 'cli_path', return_value='/official/claude'), \
                patch.object(cli, '_check_isolation'), \
                patch.object(cli, '_run', return_value=result({'loggedIn': True,
                     'authMethod': 'claude.ai', 'email': 'private@example.test', 'accessToken': 'PRIVATE'})):
            status = cli.auth_status()
        self.assertTrue(status['subscription_auth'])
        self.assertNotIn('PRIVATE', json.dumps(status))
        self.assertNotIn('email', status)

    def test_uninstalled_or_broken_status_is_clear(self):
        with patch.object(cli, 'cli_path', side_effect=PipelineError('missing')):
            self.assertEqual(cli.auth_status(), {'installed': False, 'logged_in': False})
        with patch.object(cli, 'cli_path', return_value='/official/claude'), \
                patch.object(cli, '_check_isolation', side_effect=PipelineError('unknown option PRIVATE')):
            self.assertEqual(cli.auth_status()['status'], 'unavailable')

    def test_missing_required_isolation_blocks_before_generation(self):
        help_output = Mock(stdout='--tools --output-format', returncode=0)
        with patch.object(cli, '_run', return_value=help_output) as run:
            with self.assertRaisesRegex(PipelineError, 'isolation'):
                cli._check_isolation('/official/claude', {})
        run.assert_called_once()

    def test_api_key_authentication_is_not_silently_used(self):
        with patch.object(cli, 'cli_path', return_value='/official/claude'), \
                patch.object(cli, '_check_isolation'), \
                patch.object(cli, 'auth_status', return_value={'logged_in': True, 'method': 'api_key', 'subscription_auth': False}), \
                patch.object(cli, '_run') as run:
            with self.assertRaisesRegex(PipelineError, 'subscription login'):
                cli.generate_json('topic', 'system')
        run.assert_not_called()

    def test_json_generation_uses_stdin_and_disables_agent_capabilities(self):
        with patch.object(cli, 'cli_path', return_value='/official/claude'), \
                patch.object(cli, '_check_isolation'), \
                patch.object(cli, 'auth_status', return_value={'logged_in': True, 'subscription_auth': True}), \
                patch.object(cli, '_run', return_value=result({'result': '{"ready":true}', 'is_error': False})) as run:
            self.assertEqual(cli.generate_json('secret-free topic', 'medical source rules', 700), '{"ready":true}')
        arguments = run.call_args.args[0]
        self.assertNotIn('secret-free topic', arguments)
        self.assertEqual(run.call_args.kwargs['prompt'], 'secret-free topic')
        self.assertEqual(arguments[arguments.index('--tools')+1], '')
        for flag in cli.REQUIRED_FLAGS:
            self.assertIn(flag, arguments)
        env = run.call_args.kwargs['env']
        self.assertEqual(env['CLAUDE_CODE_MAX_RETRIES'], '0')
        self.assertEqual(env['CLAUDE_CODE_MAX_TURNS'], '1')
        self.assertEqual(env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'], '700')

    def test_provider_failure_is_sanitized_and_not_retried(self):
        with patch.object(cli, 'cli_path', return_value='/official/claude'), \
                patch.object(cli, '_check_isolation'), \
                patch.object(cli, 'auth_status', return_value={'logged_in': True, 'subscription_auth': True}), \
                patch.object(cli, '_run', return_value=result({'result': 'PRIVATE', 'is_error': True}, 1)) as run:
            with self.assertRaises(PipelineError) as caught:
                cli.generate_json('topic', 'system')
        run.assert_called_once()
        self.assertNotIn('PRIVATE', str(caught.exception))

    def test_non_json_response_is_not_accepted(self):
        with patch.object(cli, 'cli_path', return_value='/official/claude'), \
                patch.object(cli, '_check_isolation'), \
                patch.object(cli, 'auth_status', return_value={'logged_in': True, 'subscription_auth': True}), \
                patch.object(cli, '_run', return_value=result({'result': 'Plain prose'})):
            with self.assertRaisesRegex(PipelineError, 'JSON result'):
                cli.generate_json('topic', 'system')

    def test_subprocess_runs_in_empty_temporary_directory_and_preserves_utf8(self):
        def invoke(arguments, **kwargs):
            from pathlib import Path
            self.assertEqual(list(Path(kwargs['cwd']).iterdir()), [])
            self.assertEqual(kwargs['encoding'], 'utf-8')
            self.assertNotIn('shell', kwargs)
            return result({'result': '{}'})
        with patch.object(cli.subprocess, 'run', side_effect=invoke):
            cli._run(['/official/claude'], env={}, prompt='Türkçe')

    def test_timeout_does_not_expose_subprocess_input(self):
        with patch.object(cli.subprocess, 'run', side_effect=subprocess.TimeoutExpired('PRIVATE', 3)):
            with self.assertRaises(PipelineError) as caught:
                cli._run(['/official/claude'], env={})
        self.assertNotIn('PRIVATE', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
