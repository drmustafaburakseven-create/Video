from pathlib import Path
from unittest.mock import patch

import pytest

from automation.higgsfield_avatar import CLI, arguments, job_id, quote_credits, reserve, run
from automation.state import LocalJournal, PipelineError


@pytest.mark.parametrize('quote', [
    {'usd': .1}, {'cost': 3}, {'credits': 'NaN'}, {'credits': -1},
    {'credits': True}, {'credits': 2, 'currency': 'USD'},
    {'credits': 2, 'total_credits': 8}, [],
])
def test_ambiguous_prices_cannot_start_a_charge(quote):
    with pytest.raises(PipelineError):
        quote_credits(quote)


def test_numeric_credit_quotes_and_zero_are_explicit():
    assert quote_credits({'credits': '2.5'}) == 2.5
    assert quote_credits({'cost': 0, 'currency': 'credits'}) == 0


def test_reservations_survive_unknown_provider_result_and_month_rollover(tmp_path):
    j = LocalJournal(tmp_path)
    reserve(j, 'intro', 3, 4, 5, '2026-11')
    reserve(j, 'intro', 3, 4, 5, '2026-11')  # resume, not a second charge
    with pytest.raises(PipelineError):
        reserve(j, 'outro', 3, 4, 5, '2026-11')
    reserve(j, 'outro', 3, 4, 5, '2026-12')
    assert j.load('higgsfield-credit-reservations')['2026-11'] == {'intro': '3'}


def test_zero_limits_allow_free_but_never_mean_unlimited(tmp_path):
    j = LocalJournal(tmp_path)
    reserve(j, 'free', 0, 0, 0, '2026-11')
    with pytest.raises(PipelineError):
        reserve(j, 'paid', .01, 0, 0, '2026-11')


def test_female_audio_never_replaces_the_doctor_driver():
    spec = {'model': 'wan2_6', 'mode': 'audio_driven',
            'params': {'prompt': 'Listen silently; then speak.', 'duration': 15}}
    args = arguments(spec, {'portrait': Path('/private/portrait.jpg'),
                            'audio': Path('/private/doctor-only.wav')})
    assert args[args.index('--audio')+1] == '/private/doctor-only.wav'
    assert '--wait' not in args  # get a durable job id before waiting


def test_create_response_must_identify_exactly_one_job():
    assert job_id(['12345678-abcdef']) == '12345678-abcdef'
    with pytest.raises(PipelineError):
        job_id(['12345678-abcdef', '87654321-fedcba'])


class FakeCLI:
    def __init__(self): self.calls = []
    def call(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ('model', 'get'): return {'id': 'wan2_6'}
        if args[:2] == ('generate', 'cost'): return {'credits': 3}
        if args[:2] == ('generate', 'create'): raise PipelineError('Network failed after submission')
        raise AssertionError(args)


def test_uncertain_paid_submission_is_never_sent_twice(tmp_path):
    spec = {'model': 'wan2_6', 'mode': 'audio_driven', 'episode': 'example', 'role': 'intro',
            'params': {'prompt': 'example', 'duration': 15}}
    assets = {'portrait': Path('/private/p.jpg'), 'audio': Path('/private/d.wav')}
    cli = FakeCLI()
    j = LocalJournal(tmp_path/'journal')
    with patch('automation.higgsfield_avatar.load_job', return_value=(spec, assets)):
        for _ in range(2):
            with pytest.raises(PipelineError):
                run('unused.json', tmp_path/'out', j, cli=cli, quote_only=False,
                    max_credits=3, monthly_credits=6)
    assert sum(x[:2] == ('generate', 'create') for x in cli.calls) == 1
    assert sum(x[:2] == ('generate', 'cost') for x in cli.calls) == 1


def test_quote_only_never_creates_and_budget_blocks_before_create(tmp_path):
    spec = {'model': 'wan2_6', 'mode': 'audio_driven', 'params': {'prompt': 'x'}}
    assets = {'portrait': Path('/private/p.jpg'), 'audio': Path('/private/d.wav')}
    cli = FakeCLI()
    with patch('automation.higgsfield_avatar.load_job', return_value=(spec, assets)):
        out = run('unused', tmp_path/'out', LocalJournal(tmp_path/'j'), cli=cli)
        assert out['status'] == 'quote_only'
        with pytest.raises(PipelineError):
            run('unused', tmp_path/'out', LocalJournal(tmp_path/'j'), cli=cli,
                quote_only=False, max_credits=2, monthly_credits=20)
    assert not any(x[:2] == ('generate', 'create') for x in cli.calls)


def test_provider_errors_do_not_leak_tokens_or_signed_urls():
    from subprocess import CompletedProcess
    failure = CompletedProcess([], 1, '', 'request failed token=secret https://cdn.example/a?key=secret')
    with patch('automation.higgsfield_avatar.subprocess.run', return_value=failure):
        with pytest.raises(PipelineError) as e:
            CLI('higgsfield').call('account', 'status')
    assert 'secret' not in str(e.value)
