import copy
import hashlib
import unittest
from unittest.mock import patch

from automation.assembly import compile_plan
from automation.hybrid import validate
from automation.state import PipelineError


DAY = '2026-11-16'


def script():
    return {'schema': 'editorial-script-v1', 'topic_id': 'ek-gida', 'title': 'Ek gıdaya başlangıç',
            'duration_seconds': 60, 'narration': 'Yumuşak pişmiş besinleri küçük miktarda sunun. '*15,
            'sources': ['https://www.cdc.gov/infant-toddler-nutrition/foods-and-drinks/index.html'],
            'scenes': [{'start': i*4, 'duration': 4,
                        'kind': 'avatar' if i in (0, 7) else 'generated' if i in (5, 6) else 'stock',
                        'visual': 'A hand mashes cooked vegetables in a bowl.',
                        'motion_prompt': 'An adult hand gently mashes soft cooked vegetables with a fork.'}
                       for i in range(15)]}


def asset(identifier, duration=44, kind='stock', approved=True, tags=None):
    return {'kind': kind, 'duration': duration, 'source_duration': duration,
            'path': f'media/library/{identifier}.mp4', 'sha256': hashlib.sha256(identifier.encode()).hexdigest(),
            'approved_topics': ['ek-gida'] if approved else [],
            'tags': tags or ['vegetables', 'mashes', 'bowl']}


class AssemblyTests(unittest.TestCase):
    def test_44_stock_8_new_generated_8_avatar_with_unchanged_narration(self):
        original = script()
        before = copy.deepcopy(original)
        plan = compile_plan(original, {'stock-one': asset('stock-one')}, DAY)
        self.assertEqual(validate(plan), {'generated_seconds': 8, 'avatar_seconds': 8,
                                         'new_clip_count': 1, 'stock_seconds': 44})
        self.assertEqual(plan['narration'], original['narration'])
        self.assertEqual(plan['sources'], original['sources'])
        self.assertEqual(original, before)
        self.assertFalse(plan['enabled'])
        self.assertEqual(plan['format'], 'hybrid-v1')
        generated = [s for s in plan['shots'] if s.get('generation_id')]
        self.assertEqual([s['source_start'] for s in generated], [0, 4])
        self.assertEqual(generated[0]['generation_id'], generated[1]['generation_id'])
        self.assertEqual(generated[0]['prompt'], generated[1]['prompt'])
        self.assertIn('9:16', generated[0]['prompt'])

    def test_source_intervals_are_distinct_and_reusable_on_later_days(self):
        assets = {f'clip-{i}': asset(f'clip-{i}', 8) for i in range(6)}
        first = compile_plan(script(), assets, DAY)
        intervals = [(s['asset_id'], s['source_start']) for s in first['shots'] if s['kind'] == 'stock']
        self.assertEqual(len(set(intervals)), 11)
        self.assertTrue(all(offset in (0, 4) for _, offset in intervals))
        second = compile_plan(script(), assets, '2026-11-17')
        self.assertEqual(intervals, [(s['asset_id'], s['source_start']) for s in second['shots'] if s['kind'] == 'stock'])

    def test_52_seconds_of_curated_stock_avoids_all_new_generation(self):
        plan = compile_plan(script(), {'ready': asset('ready', 52)}, DAY)
        self.assertEqual(validate(plan), {'generated_seconds': 0, 'avatar_seconds': 8,
                                         'new_clip_count': 0, 'stock_seconds': 52})
        intervals = [s['source_start'] for s in plan['shots'] if s.get('asset_id') == 'ready']
        self.assertEqual(len(set(intervals)), 13)
        self.assertEqual(set(intervals), set(range(0, 52, 4)))

    def test_optional_replacements_preserve_cached_ai_provenance(self):
        plan = compile_plan(script(), {'ready-ai': asset('ready-ai', 52, kind='generated')}, DAY)
        self.assertEqual(validate(plan)['new_clip_count'], 0)
        used = [s for s in plan['shots'] if s.get('asset_id') == 'ready-ai']
        self.assertEqual(len(used), 13)
        self.assertTrue(all(s['kind'] == 'generated' for s in used))

    def test_only_four_extra_seconds_still_uses_one_shared_generated_clip(self):
        plan = compile_plan(script(), {'ready': asset('ready', 48)}, DAY)
        self.assertEqual(validate(plan)['new_clip_count'], 1)
        self.assertEqual(validate(plan)['generated_seconds'], 8)
        self.assertEqual(validate(plan)['stock_seconds'], 44)

    def test_keyword_overlap_precedes_stable_asset_id_tie_break(self):
        assets = {'a-irrelevant': asset('a-irrelevant', tags=['sleeping', 'bed']),
                  'b-vegetable': asset('b-vegetable'), 'c-vegetable': asset('c-vegetable')}
        plan = compile_plan(script(), assets, DAY)
        self.assertEqual(plan['shots'][1]['asset_id'], 'b-vegetable')

    def test_cached_generated_footage_keeps_its_synthetic_provenance(self):
        plan = compile_plan(script(), {'cached-ai': asset('cached-ai', kind='generated')}, DAY)
        reused = [s for s in plan['shots'] if s.get('asset_id') == 'cached-ai']
        self.assertEqual(len(reused), 11)
        self.assertTrue(all(s['kind'] == 'generated' and 'generation_id' not in s for s in reused))
        self.assertEqual(validate(plan)['new_clip_count'], 1)

    def test_unapproved_or_other_topic_assets_never_enter_plan(self):
        other = asset('other-topic')
        other['approved_topics'] = ['uyku']
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network')) as network:
            with self.assertRaisesRegex(PipelineError, 'onaylı ara çekim'):
                compile_plan(script(), {'unreviewed': asset('unreviewed', approved=False), 'other': other}, DAY)
            network.assert_not_called()

    def test_insufficient_total_or_short_sources_fail_before_generation(self):
        for assets in [{'too-short': asset('too-short', 3.99)}, {'forty-seconds': asset('forty-seconds', 40)}]:
            with self.subTest(assets=assets), self.assertRaisesRegex(PipelineError, 'Ücretli üretim başlatılmadı'):
                compile_plan(script(), assets, DAY)

    def test_same_file_aliases_cannot_repeat_frames_to_fill_timeline(self):
        first = asset('first', 24)
        duplicate = {**first, 'path': 'media/library/second.mp4'}
        with self.assertRaisesRegex(PipelineError, 'yalnız 24 saniye'):
            compile_plan(script(), {'first': first, 'second': duplicate}, DAY)

    def test_missing_media_identity_metadata_is_not_selected(self):
        for key in ('path', 'sha256'):
            invalid = asset('invalid')
            invalid.pop(key)
            with self.subTest(key=key), self.assertRaisesRegex(PipelineError, 'onaylı ara çekim'):
                compile_plan(script(), {'invalid': invalid}, DAY)

    def test_invalid_script_timeline_kinds_source_or_narration_rejected(self):
        changes = []
        wrong = script()
        wrong['scenes'][2]['duration'] = 3
        changes.append(wrong)
        wrong = script()
        wrong['scenes'][5]['kind'] = 'stock'
        changes.append(wrong)
        wrong = script()
        wrong['scenes'][0]['start'] = False
        changes.append(wrong)
        wrong = script()
        wrong['sources'] = ['http://example.com']
        changes.append(wrong)
        wrong = script()
        wrong['narration'] = 'Kısa'
        changes.append(wrong)
        wrong = script()
        wrong['schema'] = 'invented'
        changes.append(wrong)
        wrong = script()
        wrong['scenes'][1]['asset_id'] = 'invented'
        changes.append(wrong)
        for invalid in changes:
            with self.subTest(invalid=invalid), self.assertRaises(PipelineError):
                compile_plan(invalid, {'clip': asset('clip')}, DAY)

    def test_long_topic_ids_stay_valid_and_catalog_wrapper_is_supported(self):
        original = script()
        original['topic_id'] = 'a'*64
        clip = asset('clip')
        clip['approved_topics'] = [original['topic_id']]
        plan = compile_plan(original, {'version': 1, 'assets': {'clip': clip}}, DAY)
        self.assertLessEqual(len(plan['id']), 64)
        self.assertTrue(plan['id'].startswith(DAY))
        validate(plan)


if __name__ == '__main__':
    unittest.main()
