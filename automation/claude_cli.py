"""Official Claude Code subscription client, isolated from repository tools/hooks.

Uses the user's normal Claude login. It never extracts browser credentials or
falls back to separately billed API providers. Managed organization policy is
still enforced by the official CLI; safe mode disables user customizations.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from automation.state import PipelineError

DEFAULT_CLI = Path('/workspace/video-tools/claude-code/node_modules/.bin/claude')
REQUIRED_FLAGS = ('--safe-mode', '--tools', '--output-format', '--system-prompt',
                  '--no-session-persistence', '--strict-mcp-config', '--mcp-config',
                  '--disable-slash-commands', '--no-chrome', '--permission-prompts')
SUBSCRIPTION_METHODS = {'claude.ai', 'oauth_token'}
PRESERVED_AUTH = {'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_CONFIG_DIR', 'CLAUDE_CONFIG_DIR'}
CONFLICTING_AUTH = {'AWS_BEARER_TOKEN_BEDROCK', 'CLAUDE_CODE_GATEWAY_TOKEN_FILE_DESCRIPTOR'}


def subscription_environment(source=None):
    """Keep OAuth, proxy and CA bindings; remove routes to API-key billing."""
    env = dict(os.environ if source is None else source)
    for name in list(env):
        if name in PRESERVED_AUTH:
            continue
        if (name.startswith(('ANTHROPIC_', 'CLAUDE_CODE_USE_')) or
                name in CONFLICTING_AUTH or
                (name.startswith('CLAUDE_CODE_SKIP_') and name.endswith('_AUTH'))):
            env.pop(name)
    return env


def cli_path():
    configured = os.environ.get('CLAUDE_CLI_PATH') or os.environ.get('CLI_PATH')
    candidate = configured or shutil.which('claude') or str(DEFAULT_CLI)
    found = shutil.which(candidate)
    if found:
        return str(Path(found).resolve())
    raise PipelineError('Claude Code is not installed. Install the official @anthropic-ai/claude-code package.')


def _run(arguments, *, env, prompt=None, timeout=30):
    # A fresh empty directory keeps project instructions and repo contents out.
    with tempfile.TemporaryDirectory(prefix='video-claude-') as directory:
        try:
            return subprocess.run(arguments, input=prompt, capture_output=True,
                                  text=True, encoding='utf-8', errors='replace',
                                  cwd=directory, env=env, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise PipelineError('Claude Code timed out; no automatic retry was made.') from None
        except OSError:
            raise PipelineError('Claude Code could not start.') from None


def _check_isolation(path, env):
    result = _run([path, '--help'], env=env)
    if result.returncode or any(flag not in result.stdout for flag in REQUIRED_FLAGS):
        raise PipelineError('Claude Code lacks required isolation options; update the official CLI before use.')


def auth_status():
    """Return connection state only; omit email, account IDs and credentials."""
    try:
        path = cli_path()
    except PipelineError:
        return {'installed': False, 'logged_in': False}
    env = subscription_environment()
    try:
        _check_isolation(path, env)
        result = _run([path, '--safe-mode', 'auth', 'status', '--json'], env=env)
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or type(data.get('loggedIn')) is not bool:
            raise ValueError('Invalid auth metadata')
    except (PipelineError, ValueError, TypeError):
        return {'installed': True, 'logged_in': False, 'status': 'unavailable'}
    method = data.get('authMethod')
    # Accept only known public labels; never reflect arbitrary provider strings.
    method = method if method in SUBSCRIPTION_METHODS | {'none', 'api_key', 'apiKey', 'console', 'thirdParty'} else 'unknown'
    return {'installed': True, 'logged_in': data['loggedIn'] and result.returncode == 0,
            'method': method, 'subscription_auth': method in SUBSCRIPTION_METHODS}


def generate_json(prompt, system, max_output_tokens=6000):
    """Generate one JSON object/array through an already authenticated subscription.

    Caller must journal this invocation before calling it. There is no network
    retry, provider fallback, login attempt or interactive permission request.
    """
    if not isinstance(prompt, str) or not prompt.strip() or not isinstance(system, str) or not system.strip():
        raise PipelineError('Claude needs a non-empty prompt and system instruction.')
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 32000:
        raise PipelineError('Claude output token limit must be between 1 and 32000.')
    path = cli_path()
    env = subscription_environment()
    _check_isolation(path, env)
    status = auth_status()
    if not status.get('logged_in') or not status.get('subscription_auth'):
        raise PipelineError('Claude subscription login is required: run claude auth login --claudeai.')
    env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] = str(max_output_tokens)
    env['CLAUDE_CODE_MAX_TURNS'] = '1'
    env['CLAUDE_CODE_MAX_RETRIES'] = '0'
    arguments = [path, '-p', '--output-format', 'json', '--tools', '', '--safe-mode',
                 '--no-session-persistence', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                 '--disable-slash-commands', '--no-chrome', '--permission-prompts', 'none',
                 '--system-prompt', system]
    model = os.environ.get('CLAUDE_CODE_MODEL')
    if model:
        if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', model):
            raise PipelineError('Invalid Claude Code model selector.')
        arguments += ['--model', model]
    result = _run(arguments, env=env, prompt=prompt, timeout=300)
    try:
        payload = json.loads(result.stdout)
        if result.returncode or not isinstance(payload, dict) or payload.get('is_error'):
            raise ValueError('CLI generation failed')
        text = payload.get('result')
        decoded = json.loads(text)
        if not isinstance(decoded, (dict, list)):
            raise ValueError('Structured content is required')
    except (ValueError, TypeError):
        # CLI output/errors can include provider metadata; do not echo them.
        raise PipelineError('Claude did not return a successful JSON result; inspect its saved operation before retrying.') from None
    return text


if __name__ == '__main__':
    print(json.dumps(auth_status()))
