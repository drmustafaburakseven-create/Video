import json
from unittest.mock import patch

import pytest

from automation.higgsfield_avatar import sha
from automation.higgsfield_episode import assemble, main, phone_copy
from automation.state import PipelineError


def test_cannot_assemble_before_new_avatar_review(tmp_path):
    script = tmp_path/'script.json'; script.write_text('{}')
    template = tmp_path/'template.json'; template.write_text('{}')
    package = {key: {'path': path.name, 'sha256': sha(path)}
               for key, path in [('script', script), ('ready_template', template)]}
    with patch('automation.higgsfield_episode.ready_reel.render') as render:
        with pytest.raises(PipelineError, match='incelemesi'):
            assemble(tmp_path, package, tmp_path/'final')
        render.assert_not_called()


def test_quotes_both_roles_before_any_generation(tmp_path):
    package = tmp_path/'episode.json'
    package.write_text(json.dumps({'schema': 'higgsfield-episode-v1',
                                   'jobs': {'intro': 'intro.json', 'outro': 'outro.json'}}))
    calls = []
    def quote(job, *args, **kw):
        calls.append((job.name, kw['quote_only']))
        if job.name == 'outro.json': raise PipelineError('Closing model unavailable')
        return {'status': 'quote_only', 'credits': '1'}
    with patch('automation.higgsfield_episode.higgsfield_avatar.run', side_effect=quote):
        assert main([str(package), '--stage', 'avatars', '--journal', str(tmp_path/'journal')]) == 2
    assert calls == [('intro.json', True), ('outro.json', True)]


def test_old_phone_copy_cannot_be_returned_for_a_different_master(tmp_path):
    master = tmp_path/'master.mp4'; master.write_bytes(b'new')
    phone = tmp_path/'phone.mp4'; phone.write_bytes(b'old')
    phone.with_suffix('.validation.json').write_text(json.dumps({
        'source_sha256': 'old-source', 'output_sha256': sha(phone)}))
    with pytest.raises(PipelineError, match='eşleşmiyor'):
        phone_copy(master, phone)
