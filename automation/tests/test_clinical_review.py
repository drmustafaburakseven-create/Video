import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation.clinical_review import check
from automation.hybrid_render import validate_segments
from automation.state import PipelineError


class ClinicalReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'clip.mp4'
        self.path.write_bytes(b'original footage')
        self.review = self.path.with_name(self.path.name+'.clinical-review.json')

    def record(self, status):
        self.review.write_text(json.dumps({'status': status,
            'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest()}))

    def test_rejected_or_pending_clips_cannot_reenter_a_render(self):
        for status in ['rejected', 'review_required']:
            self.record(status)
            with patch('automation.hybrid_render.probe') as probe:
                with self.assertRaisesRegex(PipelineError, 'clinical review'):
                    validate_segments([{'path': self.path, 'kind': 'generated', 'duration': 60}])
                probe.assert_not_called()

    def test_approval_applies_only_to_the_reviewed_bytes(self):
        self.record('approved')
        check(self.path)
        self.path.write_bytes(b'different hand movement')
        with self.assertRaisesRegex(PipelineError, 'stale'):
            check(self.path)

    def test_unmarked_media_remains_usable_and_malformed_review_does_not(self):
        check(self.path)
        self.review.write_text('{}')
        with self.assertRaises(PipelineError):
            check(self.path)
