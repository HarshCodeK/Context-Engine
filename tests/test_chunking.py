import unittest

from context_studio.chunking import structure_aware_chunks


class StructureAwareChunkingTests(unittest.TestCase):
    def test_keeps_small_document_as_one_chunk(self):
        self.assertEqual(structure_aware_chunks('# Notes\n\nA short paragraph.'), ['# Notes\n\nA short paragraph.'])

    def test_splits_on_paragraph_boundaries_and_respects_maximum(self):
        paragraphs = [f'Paragraph {index}. ' + ('useful context ' * 9) for index in range(8)]
        chunks = structure_aware_chunks('\n\n'.join(paragraphs), max_chars=260, overlap_chars=30)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 260 for chunk in chunks))
        self.assertTrue(all(chunk.strip() for chunk in chunks))

    def test_splits_long_sentences_without_dropping_words(self):
        words = [f'term{index}' for index in range(180)]
        text = ' '.join(words) + '.'
        chunks = structure_aware_chunks(text, max_chars=180, overlap_chars=20)
        joined = ' '.join(chunks)
        for word in words:
            self.assertIn(word, joined)
        self.assertTrue(all(len(chunk) <= 180 for chunk in chunks))

    def test_rejects_invalid_chunk_limits(self):
        with self.assertRaises(ValueError):
            structure_aware_chunks('text', max_chars=50)
        with self.assertRaises(ValueError):
            structure_aware_chunks('text', max_chars=100, overlap_chars=100)


if __name__ == '__main__':
    unittest.main()
