"""Readable, lightly animated captions and independently timed emphasis cards."""
import re
from pathlib import Path

from automation.render import captions, timestamp


def safe(text):
    return text.replace('\\', '').replace('{', '').replace('}', '').replace('\n', r'\N')


def write(alignment, directory, delay=0, *, beats=()):
    """Validate original alignment, retaining SRT; add short ASS caption groups."""
    last = captions(alignment, directory, delay)
    path = Path(directory)/'captions.ass'
    lines = [line for line in path.read_text().splitlines()
             if not (line.startswith('Dialogue:') and ',Subtitle,' in line)]
    chars = alignment['characters']
    starts = alignment['character_start_times_seconds']
    ends = alignment['character_end_times_seconds']
    offsets = [i for i, char in enumerate(chars) for _ in char]
    words = [(m.group(), starts[offsets[m.start()]]+delay, ends[offsets[m.end()-1]]+delay)
             for m in re.finditer(r'\S+', ''.join(chars))]
    groups, group = [], []
    for word in words:
        if group and (len(group) >= 4 or len(' '.join(w[0] for w in group+[word])) > 29
                      or word[1]-group[-1][2] > .5):
            groups.append(group)
            group = []
        group.append(word)
        if word[0][-1:] in '.!?;:':
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    for group in groups:
        text = safe(' '.join(w[0] for w in group))
        effect = r'{\an2\pos(340,1080)\fs38\fad(80,60)\fscx108\fscy108\t(0,150,\fscx100\fscy100)}'
        lines.append(f'Dialogue: 2,{timestamp(group[0][1])},{timestamp(group[-1][2])},Subtitle,,0,0,0,,{effect}{text}')
    colors = {'yellow': '49D9FF', 'pink': 'A874FF', 'cream': 'EEF7FF'}
    for beat in beats:
        start, end = beat['start'], beat['end']
        if not 0 <= start < end <= 60 or beat.get('color', 'yellow') not in colors:
            raise ValueError('Invalid emphasis card timing or color.')
        color = colors[beat.get('color', 'yellow')]
        y = beat.get('y', 180)
        effect = (r'{\an8\pos(340,'+str(y)+r')\fs44\bord5\c&H'+color+
                  r'&\fad(120,100)\fscx108\fscy108\t(0,160,\fscx100\fscy100)}')
        lines.append(f'Dialogue: 3,{timestamp(start)},{timestamp(end)},Subtitle,,0,0,0,,{effect}{safe(beat["text"])}')
    path.write_text('\n'.join(lines)+'\n')
    return last
