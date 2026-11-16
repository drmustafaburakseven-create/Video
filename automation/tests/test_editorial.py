"""Daily topic rotation, source grounding and no-repeat drafting checks."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from automation import editorial
from automation.state import LocalJournal, PipelineError


DAY = '2026-11-16'
URL = 'https://www.cdc.gov/infant-toddler-nutrition/example'


def topics(count=5):
    return [{'id': f'topic-{i}', 'title': f'Konu {i}', 'age_group': '6–12 ay', 'sources': [URL]}
            for i in range(count)]


def evidence():
    return {URL: {'text': 'Official evidence about safe complementary foods. '*10,
                  'retrieved_at': DAY+'T09:00:00+03:00'}}


def script(topic_id='topic-0'):
    chunks = ['Ek gıdaya ne zaman başlamalı?'] + [
        'Bebeğinizin hazır oluşunu gözleyin ve yumuşak besinleri küçük miktarda sunun.'
    ]*13 + ['Bu videoyu kaydedin.']
    return {'topic_id': topic_id, 'title': 'Ek gıdaya başlangıç', 'age_group': '6–12 ay',
            'hooks': [{'kind': 'daily', 'text': chunks[0]},
                      {'kind': 'myth', 'text': 'Her bebeğin hazırlığı aynı değildir.'},
                      {'kind': 'question', 'text': 'Bebeğiniz hazır mı?'}],
            'selected_hook': 0, 'selection_reason': 'Günlük bir soruya hemen cevap verir.',
            'narration': ' '.join(chunks), 'cta': chunks[-1], 'sources': [URL],
            'scenes': [{'start': i*4, 'duration': 4, 'kind': 'avatar' if i in [0, 7] else 'stock',
                        'speech': chunk, 'screen_text': '', 'visual': 'Yumuşak besin hazırlanıyor.',
                        'motion_prompt': 'Portrait 9:16 adult hand gently mashes soft cooked vegetables.'}
                       for i, chunk in enumerate(chunks)]}


def gemini_result(value=None):
    return {'candidates': [{'content': {'parts': [{'text': json.dumps(value or {'scripts': [script()]})}]}}]}


class TopicSelectionTests(unittest.TestCase):
    def test_rotation_prefers_unused_then_oldest_and_is_stable(self):
        catalog = topics(7)
        history = [{'date': '2026-11-15', 'topic_ids': ['topic-0', 'topic-1']}]
        first = editorial.propose_topics(DAY, catalog, history)
        self.assertEqual(first, editorial.propose_topics(DAY, {'topics': catalog}, history))
        self.assertEqual({t['id'] for t in first}, {f'topic-{i}' for i in range(2, 7)})
        history.append({'date': '2026-11-10', 'topic_id': 'topic-2'})
        self.assertEqual(editorial.propose_topics(DAY, catalog, history)[-1]['id'], 'topic-2')

    def test_catalog_duplicates_bad_dates_and_short_lists_fail(self):
        for day, catalog in [('not-date', topics()), (DAY, topics(4)), (DAY, [topics()[0]]*5)]:
            with self.subTest(day=day, count=len(catalog)), self.assertRaises(PipelineError):
                editorial.propose_topics(day, catalog, [])


class EditorialValidationTests(unittest.TestCase):
    def test_valid_script_stays_disabled_and_unmeasured(self):
        result = editorial.validate_response({'scripts': [script()]}, topics(), 1)[0]
        self.assertFalse(result['enabled'])
        self.assertFalse(result['duration_verified'])
        self.assertNotIn('shots', result)
        self.assertEqual(sum(s['duration'] for s in result['scenes']), 60)

    def test_topic_age_and_source_changes_are_rejected(self):
        for field, value in [('topic_id', 'invented-topic'), ('age_group', '0–3 ay'),
                             ('sources', ['https://unverified.example/claim'])]:
            altered = script()
            altered[field] = value
            with self.subTest(field=field), self.assertRaises(PipelineError):
                editorial.validate_response({'scripts': [altered]}, topics(), 1)

    def test_changed_scene_speech_and_fake_media_ids_are_rejected(self):
        altered = script()
        altered['scenes'][1]['speech'] = 'Bu ek iddia metinde yok.'
        with self.assertRaisesRegex(PipelineError, 'without adding or omitting'):
            editorial.validate_response({'scripts': [altered]}, topics(), 1)
        altered = script()
        altered['scenes'][1]['asset_id'] = 'imaginary-stock'
        with self.assertRaisesRegex(PipelineError, 'cannot invent'):
            editorial.validate_response({'scripts': [altered]}, topics(), 1)

    def test_wrong_opening_cta_and_timeline_are_rejected(self):
        cases = []
        changed = script()
        changed['selected_hook'] = 1
        cases.append(changed)
        changed = script()
        changed['cta'] = 'Beni takip edin.'
        cases.append(changed)
        changed = script()
        changed['scenes'][2]['start'] = 9
        cases.append(changed)
        changed = script()
        changed['scenes'][0]['start'] = False
        cases.append(changed)
        for item in cases:
            with self.subTest(item=item['selected_hook']), self.assertRaises(PipelineError):
                editorial.validate_response({'scripts': [item]}, topics(), 1)


class StoryboardCompilerTests(unittest.TestCase):
    def content(self):
        value = script()
        value.pop('scenes')
        value['broll'] = [{'screen_text': f'Kısa yazı {i}', 'visual': f'Hareketli ara çekim {i}',
                           'motion_prompt': f'Portrait 9:16 shot {i}: an adult gently prepares soft food.'}
                          for i in range(13)]
        return {'scripts': [value]}

    def test_canonical_narration_is_distributed_without_added_or_missing_words(self):
        value = self.content()
        narration = value['scripts'][0]['narration'].replace(' ', '\n', 2)
        value['scripts'][0]['narration'] = narration
        compiled = editorial.compile_storyboard(value)['scripts'][0]
        self.assertEqual(compiled['narration'], narration)
        self.assertEqual(' '.join(s['speech'] for s in compiled['scenes']).split(), narration.split())
        self.assertNotIn('broll', compiled)
        # Compiling an already compiled receipt is idempotent.
        before = copy.deepcopy(value)
        self.assertEqual(editorial.compile_storyboard(value), before)
        editorial.validate_response(value, topics(), 1)

    def test_media_counts_positions_and_broll_order_are_deterministic(self):
        compiled = editorial.compile_storyboard(self.content())['scripts'][0]
        scenes = compiled['scenes']
        self.assertEqual([s['start'] for s in scenes], list(range(0, 60, 4)))
        self.assertEqual([s['duration'] for s in scenes], [4]*15)
        self.assertEqual([i for i, s in enumerate(scenes) if s['kind'] == 'avatar'], [0, 7])
        self.assertEqual([i for i, s in enumerate(scenes) if s['kind'] == 'generated'], [5, 6])
        self.assertEqual(sum(s['duration'] for s in scenes if s['kind'] == 'stock'), 44)
        self.assertEqual([s['visual'] for s in scenes if s['kind'] != 'avatar'],
                         [f'Hareketli ara çekim {i}' for i in range(13)])
        self.assertTrue(all('asset_id' not in scene for scene in scenes))

    def test_invalid_broll_count_object_and_short_narration_are_rejected(self):
        cases = []
        item = self.content()
        item['scripts'][0]['broll'].pop()
        cases.append(item)
        item = self.content()
        item['scripts'][0]['broll'][3] = 'not an object'
        cases.append(item)
        item = self.content()
        item['scripts'][0]['narration'] = 'Çok kısa anlatım.'
        cases.append(item)
        for value in cases:
            with self.subTest(value=value['scripts'][0]['narration'][:20]), self.assertRaises(PipelineError):
                editorial.compile_storyboard(value)

    def test_compiler_does_not_bypass_source_and_visual_validation(self):
        value = self.content()
        value['scripts'][0]['sources'] = ['https://unverified.example/claim']
        with self.assertRaisesRegex(PipelineError, 'outside the verified'):
            editorial.validate_response(editorial.compile_storyboard(value), topics(), 1)
        value = self.content()
        value['scripts'][0]['broll'][2]['motion_prompt'] = ''
        with self.assertRaisesRegex(PipelineError, 'motion prompt'):
            editorial.validate_response(editorial.compile_storyboard(value), topics(), 1)


class InsufficientEvidenceTests(unittest.TestCase):
    def test_structured_schema_allows_abort_and_parser_stops_without_drafting(self):
        schema = editorial.response_schema(1)
        self.assertEqual(schema['required'], ['scripts'])
        self.assertEqual(schema['properties']['scripts']['minItems'], 0)
        self.assertEqual(schema['properties']['scripts']['maxItems'], 1)
        self.assertEqual(schema['properties']['blocked_reason']['type'], 'string')
        stopped = gemini_result({'scripts': [], 'blocked_reason': 'insufficient source evidence'})
        with patch('automation.editorial._submit') as submit:
            with self.assertRaisesRegex(PipelineError, 'insufficient source evidence'):
                editorial._text(stopped, 'gemini')
        submit.assert_not_called()


class DraftRecoveryTests(unittest.TestCase):
    def test_new_process_and_new_retrieval_time_reuse_saved_paid_result(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                patch('automation.editorial._submit', return_value=gemini_result()) as submit:
            root = Path(directory)
            first = editorial.create_daily(DAY, topics(), evidence(), LocalJournal(root/'journal'), root/'one')
            refreshed = copy.deepcopy(evidence())
            refreshed[URL]['retrieved_at'] = DAY+'T12:00:00+03:00'
            with patch.dict(os.environ, {}, clear=True):
                second = editorial.create_daily(DAY, topics(), refreshed, LocalJournal(root/'journal'), root/'two')
            submit.assert_called_once()
            self.assertEqual(first['paid_request_receipt'], second['paid_request_receipt'])
            self.assertTrue((root/'two/daily.md').exists())
            self.assertTrue((root/'two/topic-0.editorial.json').exists())

    def test_invalid_model_json_is_saved_and_not_charged_again(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                patch('automation.editorial._submit', return_value=gemini_result({'scripts': []})) as submit:
            root = Path(directory)
            for _ in range(2):
                with self.assertRaisesRegex(PipelineError, 'wrong script count'):
                    editorial.create_daily(DAY, topics(), evidence(), LocalJournal(root/'journal'), root/'out')
            submit.assert_called_once()

    def test_missing_source_or_provider_key_never_sends_request(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                patch('automation.editorial._submit') as submit:
            root = Path(directory)
            with self.assertRaisesRegex(PipelineError, 'source evidence'):
                editorial.create_daily(DAY, topics(), {}, LocalJournal(root/'journal'), root/'out')
            with self.assertRaisesRegex(PipelineError, 'credential is unavailable'):
                editorial.create_daily(DAY, topics(), evidence(), LocalJournal(root/'journal'), root/'out')
            submit.assert_not_called()

    def test_timeout_is_not_retried_in_later_process(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                patch('automation.editorial._submit', side_effect=TimeoutError('private provider detail')) as submit:
            root = Path(directory)
            with self.assertRaises(TimeoutError):
                editorial.create_daily(DAY, topics(), evidence(), LocalJournal(root/'journal'), root/'out')
            with self.assertRaisesRegex(PipelineError, 'resubmission blocked'):
                editorial.create_daily(DAY, topics(), evidence(), LocalJournal(root/'journal'), root/'out')
            submit.assert_called_once()

    def test_five_video_option_rejects_single_script_response(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                patch('automation.editorial._submit', return_value=gemini_result()):
            root = Path(directory)
            with self.assertRaisesRegex(PipelineError, 'wrong script count'):
                editorial.create_daily(DAY, topics(), evidence(), LocalJournal(root/'journal'), root/'out', videos=5)

    def test_gemini_request_has_bounded_json_output_and_no_retry_wrapper(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                patch('automation.editorial.request') as send:
            send.return_value = Mock()
            send.return_value.json.return_value = gemini_result()
            editorial._submit('gemini', editorial.DEFAULT_MODELS['gemini'], 'Grounded prompt', 1)
            self.assertEqual(send.call_count, 1)
            payload = send.call_args.kwargs['json']['generationConfig']
            self.assertEqual(payload['responseMimeType'], 'application/json')
            self.assertLessEqual(payload['maxOutputTokens'], 9000)
            script_schema = payload['responseJsonSchema']['properties']['scripts']['items']
            self.assertEqual(script_schema['properties']['broll']['minItems'], 13)
            self.assertEqual(script_schema['properties']['broll']['maxItems'], 13)


if __name__ == '__main__':
    unittest.main()
