import hashlib
import unittest

from context_studio.summarization import build_extractive_digest


class ExtractiveDigestTests(unittest.TestCase):
    def _node(self, node_id, text, locator=None):
        return {
            'id': node_id,
            'content': text,
            'locator': locator or {'type': 'page', 'page': 1},
            'content_sha256': hashlib.sha256(text.encode()).hexdigest(),
        }

    def test_digest_selects_important_sentences_and_keeps_exact_evidence_spans(self):
        text = (
            'The programme has several general workstreams and routine administrative tasks. '
            'The approved launch date is 19 May 2027, following the board decision recorded on 12 May. '
            'The operations lead owns the readiness review and must close all safety actions before launch. '
            'The team meets every week to review progress and discuss open questions.'
        )
        node = self._node('node-1', text, {'type': 'page', 'page': 4})
        digest = build_extractive_digest([node], max_sentences=3)
        self.assertIn('approved launch date', digest['text'].lower())
        self.assertIn('readiness review', digest['text'].lower())
        self.assertLessEqual(digest['summary_characters'], digest['input_characters'])
        for evidence in digest['evidence']:
            passage = text[evidence['start_offset']:evidence['end_offset']]
            self.assertEqual(hashlib.sha256(passage.encode()).hexdigest(), evidence['sentence_sha256'])
            self.assertEqual(evidence['locator'], {'type': 'page', 'page': 4})

    def test_digest_is_deterministic_and_respects_limits(self):
        text = ' '.join(
            f'The delivery decision number {index} assigns owner team {index} and deadline {index + 10} May 2027.'
            for index in range(30)
        )
        node = self._node('node-1', text)
        first = build_extractive_digest([node], max_sentences=5, max_chars=650)
        second = build_extractive_digest([node], max_sentences=5, max_chars=650)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first['evidence']), 5)
        self.assertLessEqual(first['summary_characters'], 650)

    def test_digest_prefers_coverage_across_structured_source_nodes(self):
        nodes = [
            self._node('overview', 'The programme serves small organisations across three districts and combines local installation partners with a shared maintenance desk.'),
            self._node('decision', 'The board approved the revised launch date of 19 May 2027 after the engineering review closed the roof safety issue.'),
            self._node('owner', 'The operations director owns the readiness review and must confirm the emergency isolation procedure before commissioning.'),
        ]
        digest = build_extractive_digest(nodes, max_sentences=3)
        self.assertEqual({item['node_id'] for item in digest['evidence']}, {'overview', 'decision', 'owner'})
        self.assertIn('19 May 2027', digest['text'])
        self.assertIn('operations director', digest['text'])

    def test_empty_or_non_prose_nodes_return_an_empty_digest(self):
        digest = build_extractive_digest([self._node('node-1', 'Table: A | B')])
        self.assertEqual(digest['text'], '')
        self.assertEqual(digest['evidence'], [])

    def test_invalid_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            build_extractive_digest([], max_sentences=0)
        with self.assertRaises(ValueError):
            build_extractive_digest([], max_chars=50)


if __name__ == '__main__':
    unittest.main()
