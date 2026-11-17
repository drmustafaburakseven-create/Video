"""Enforce explicit instructional-media review records without inventing approval."""
import hashlib
import json
from pathlib import Path

from automation.state import PipelineError


def check(path):
    """Unmarked media is unchanged; a review record fails closed until approved."""
    path = Path(path)
    review = path.with_name(path.name+'.clinical-review.json')
    if not review.exists():
        return
    try:
        data = json.loads(review.read_text())
        if not isinstance(data, dict) or data.get('status') not in {
                'approved', 'rejected', 'review_required'}:
            raise ValueError
        if data.get('sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise PipelineError('Instructional-media review is invalid or stale; inspect the actual footage.') from None
    if data['status'] != 'approved':
        raise PipelineError('Instructional footage has an unresolved or rejected clinical review; do not reuse it.')
