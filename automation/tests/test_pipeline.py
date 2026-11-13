import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from automation import pipeline
from automation.render import captions, probe, render
from automation.state import GitHubJournal, LocalJournal, PipelineError, paid_once


class PaidOperationTests(unittest.TestCase):
    def test_completed_request_survives_new_process_without_resubmission(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = LocalJournal(directory)
            submit = Mock(return_value={'name': 'operations/paid-once'})
            state = {}
            paid_once(journal, 'job', state, 'shot-01', submit)
            recovered = LocalJournal(directory).load('job')
            value = paid_once(journal, 'job', recovered, 'shot-01', submit)
            self.assertEqual(value['name'], 'operations/paid-once')
            submit.assert_called_once()

    def test_ambiguous_timeout_never_resubmits(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = LocalJournal(directory)
            submit = Mock(side_effect=TimeoutError('potentially charged'))
            with self.assertRaises(TimeoutError):
                paid_once(journal, 'job', {}, 'voice', submit)
            recovered = journal.load('job')
            with self.assertRaisesRegex(PipelineError, 'resubmission blocked'):
                paid_once(journal, 'job', recovered, 'voice', submit)
            submit.assert_called_once()

    def test_checkpoint_failure_prevents_paid_call(self):
        journal = Mock()
        journal.save.side_effect = OSError('state unavailable')
        submit = Mock()
        with self.assertRaises(OSError):
            paid_once(journal, 'job', {}, 'shot-01', submit)
        submit.assert_not_called()

    def test_github_large_journal_uses_raw_content_not_empty_base64(self):
        with patch('automation.state.session') as factory:
            client = factory.return_value
            client.get.return_value = Mock(status_code=200)
            client.get.return_value.json.return_value = {'sha': 'version', 'encoding': 'none', 'content': ''}
            client.request.return_value = Mock(status_code=200)
            client.request.return_value.json.return_value = {'voice': {'status': 'received'}}
            journal = GitHubJournal('owner/repo', 'fake-not-a-real-key', 'a'*40)
            self.assertIn('voice', journal.load('job'))
            self.assertEqual(journal.shas['job'], 'version')
            self.assertEqual(client.request.call_args.kwargs['headers']['Accept'],
                             'application/vnd.github.raw+json')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.plan = pipeline.load_plan(pipeline.ROOT/'plans/ek-gida-baslangic.json')

    def test_changing_model_or_narration_changes_receipt_identity(self):
        one = pipeline.job_name(self.plan, 'model-a', 'voice', False)
        self.assertNotEqual(one, pipeline.job_name(self.plan, 'model-b', 'voice', False))
        changed = {**self.plan, 'narration': self.plan['narration'] + ' Yeni cümle.'}
        self.assertNotEqual(one, pipeline.job_name(changed, 'model-a', 'voice', False))

    def test_too_many_shots_rejected_before_provider_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'plan.json'
            p.write_text(json.dumps({**self.plan, 'shots': self.plan['shots'] * 2}))
            with self.assertRaises(PipelineError):
                pipeline.load_plan(p)

    def test_missing_credentials_are_reported_without_network(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as directory:
            with patch('automation.pipeline.make_video') as generate:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = pipeline.main(['--output', directory])
                self.assertEqual(code, 2)
                generate.assert_not_called()
                status = json.loads((Path(directory)/'status.json').read_text())
                self.assertIn('GEMINI_API_KEY', status['message'])

    def test_completed_queue_does_not_require_keys_or_charge_again(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as directory:
            name = pipeline.job_name(self.plan, pipeline.VEO_MODEL, pipeline.VOICE_ID, False)
            LocalJournal(Path(directory)/'journal').save(name, {'complete': True})
            with patch('automation.pipeline.make_video') as generate:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(pipeline.main(['--output', directory]), 0)
                generate.assert_not_called()
            self.assertEqual(json.loads((Path(directory)/'status.json').read_text())['status'], 'queue_empty')

    def test_prepared_voice_reuses_existing_clone_without_elevenlabs_key(self):
        result = pipeline.prepared_voice(self.plan, pipeline.VOICE_ID)
        self.assertTrue(result['audio_base64'])
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'example'}, clear=True):
            self.assertEqual(pipeline.required_keys(False, prepared=True), [])

    def test_prepared_voice_rejects_changed_narration_or_voice(self):
        with self.assertRaises(PipelineError):
            pipeline.prepared_voice({**self.plan, 'narration': self.plan['narration']+' Test.'}, pipeline.VOICE_ID)
        with self.assertRaises(PipelineError):
            pipeline.prepared_voice(self.plan, 'different-voice')

    def test_sdk_exception_message_is_never_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            out = io.StringIO()
            with patch('automation.pipeline.load_plan', side_effect=RuntimeError('SECRET-EXAMPLE')):
                with contextlib.redirect_stdout(out):
                    self.assertEqual(pipeline.main(['--output', directory]), 2)
            self.assertNotIn('SECRET-EXAMPLE', out.getvalue())
            self.assertNotIn('SECRET-EXAMPLE', (Path(directory)/'status.json').read_text())

    def test_path_traversal_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline.main(['--plan', '../private.json', '--output', directory]), 2)

    def test_invalid_alignment_is_rejected_without_replacing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PipelineError):
                captions({'characters': ['a'], 'character_start_times_seconds': [float('nan')],
                          'character_end_times_seconds': [1]}, directory)

    def test_veo_polling_resumes_existing_operation(self):
        from google.genai import types
        veo = pipeline.Veo.__new__(pipeline.Veo)
        veo.types = types
        veo.client = Mock()
        video = types.Video(video_bytes=b'test-video')
        op = types.GenerateVideosOperation(name='operations/existing', done=True,
             response=types.GenerateVideosResponse(generated_videos=[types.GeneratedVideo(video=video)]))
        veo.client.operations.get.return_value = op
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'shot.mp4'
            veo.download({'name': 'operations/existing'}, output)
            self.assertEqual(output.read_bytes(), b'test-video')
        veo.client.models.generate_videos.assert_not_called()

    def test_omni_submission_requests_current_api_and_eight_second_portrait_video(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-only'}), patch('automation.pipeline.request') as req:
            req.return_value.json.return_value = {'id': 'v1_example', 'status': 'in_progress'}
            provider = pipeline.Omni(pipeline.VEO_MODEL)
            receipt = provider.submit('A parent gently mashes soft food.')
            self.assertEqual(receipt, {'interaction_id': 'v1_example'})
            payload = req.call_args.kwargs['json']
            self.assertEqual(payload['response_format']['duration'], '8s')
            self.assertEqual(payload['response_format']['aspect_ratio'], '9:16')
            self.assertTrue(payload['background'])
            self.assertTrue(payload['store'])

    def test_omni_resumes_and_downloads_uri_without_post_or_auth_to_external_host(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-only'}), patch('automation.pipeline.request') as req:
            completed = Mock()
            completed.json.return_value = {'status': 'completed', 'steps': [
                {'type': 'model_output', 'content': [{'type': 'video', 'uri': 'files/generated123'}]}]}
            active = Mock()
            active.json.return_value = {'state': 'ACTIVE'}
            media = Mock(content=b'mp4-test-data'*200)
            req.side_effect = [completed, active, media]
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/'clip.mp4'
                pipeline.Omni(pipeline.VEO_MODEL).download({'interaction_id': 'v1_existing'}, output)
                self.assertEqual(output.read_bytes(), media.content)
            self.assertTrue(all(call.args[1]=='GET' for call in req.call_args_list))
            self.assertTrue(all(call.args[2].startswith('https://generativelanguage.googleapis.com/')
                                for call in req.call_args_list))

    def test_omni_reports_quota_code_without_remote_error_text_or_resubmitting(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-only'}), patch('automation.pipeline.request') as req:
            req.return_value.json.return_value = {'status': 'failed', 'errors': [
                {'code': 'RESOURCE_EXHAUSTED', 'message': 'remote-private-example'}]}
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(PipelineError, 'RESOURCE_EXHAUSTED') as caught:
                    pipeline.Omni(pipeline.VEO_MODEL).download({'interaction_id': 'v1_failed'}, Path(directory)/'clip.mp4')
            self.assertNotIn('remote-private-example', str(caught.exception))
            req.assert_called_once()
            self.assertEqual(req.call_args.args[1], 'GET')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class NativeRenderTests(unittest.TestCase):
    def test_full_60_second_motion_render_has_synchronized_streams_and_captions(self):
        # This is a synthetic moving test pattern, never a user-facing finished video.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root/'moving.mp4'
            audio = root/'voice.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'testsrc2=size=180x320:rate=24:duration=8','-c:v','libx264',
                            '-preset','ultrafast','-threads','1',str(clip)], check=True)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'sine=frequency=230:sample_rate=24000:duration=58',str(audio)], check=True)
            text = 'Ek gıdaya güvenli başlangıç.'
            alignment = {'characters': list(text),
                         'character_start_times_seconds': [i*0.1 for i in range(len(text))],
                         'character_end_times_seconds': [(i+1)*0.1 for i in range(len(text))]}
            output = render([clip]*8, audio, alignment, root/'output')
            info = probe(output)
            self.assertAlmostEqual(float(info['format']['duration']), 60, places=1)
            self.assertEqual({s['codec_type'] for s in info['streams']}, {'audio','video'})
            self.assertIn('Ek gıdaya güvenli başlangıç.', (root/'output/captions.srt').read_text())
            self.assertEqual(json.loads((root/'output/validation.json').read_text())['full_decode'], 'passed')


if __name__ == '__main__':
    unittest.main()
