import hashlib
import unittest

from context_studio.document_structure import split_evidence_block


class DocumentStructureTests(unittest.TestCase):
    def test_builds_nested_heading_and_paragraph_hierarchy_with_exact_offsets(self):
        markdown = (
            '# Project brief\n\n'
            'Overview text.\n\n'
            '## Decisions\n\n'
            'The approved date is 19 May.\n\n'
            '### Approval\n\n'
            'The steering committee approved it.\n\n'
            '## Risks\n\n'
            'A supplier delay remains open.'
        )
        nodes = split_evidence_block(
            markdown,
            markdown_start=0,
            markdown_end=len(markdown),
            source_locator={'type': 'page', 'page': 2},
            block_id='block-1',
        )

        self.assertEqual(
            [(node['node_type'], node['title']) for node in nodes],
            [
                ('section', 'Project brief'),
                ('paragraph', None),
                ('section', 'Decisions'),
                ('paragraph', None),
                ('section', 'Approval'),
                ('paragraph', None),
                ('section', 'Risks'),
                ('paragraph', None),
            ],
        )
        self.assertEqual(
            [node['parent_node_key'] for node in nodes],
            [None, nodes[0]['node_key'], nodes[0]['node_key'], nodes[2]['node_key'],
             nodes[2]['node_key'], nodes[4]['node_key'], nodes[0]['node_key'], nodes[6]['node_key']],
        )
        for node in nodes:
            start = node['locator_json']['markdown_start']
            end = node['locator_json']['markdown_end']
            self.assertEqual(markdown[start:end], node['content'])
            self.assertEqual(hashlib.sha256(node['content'].encode()).hexdigest(), node['content_sha256'])
            self.assertEqual(node['locator_json']['type'], 'page')
            self.assertEqual(node['locator_json']['page'], 2)
        self.assertEqual(nodes[5]['locator_json']['section'], 'Project brief / Decisions / Approval')
        self.assertEqual(nodes[7]['locator_json']['section'], 'Project brief / Risks')

    def test_splits_unheaded_content_into_root_paragraphs(self):
        markdown = 'First paragraph contains an important decision.\n\nSecond paragraph contains a delivery risk.'
        nodes = split_evidence_block(
            markdown,
            markdown_start=10,
            markdown_end=10 + len(markdown),
            source_locator={'type': 'text_file'},
            block_id='block-2',
        )
        self.assertEqual(len(nodes), 2)
        self.assertEqual([node['node_type'] for node in nodes], ['paragraph', 'paragraph'])
        self.assertEqual([node['parent_node_key'] for node in nodes], [None, None])
        self.assertEqual(nodes[0]['locator_json']['markdown_start'], 10)
        self.assertEqual(nodes[0]['node_key'], 'block-2:part:1')

    def test_recognizes_markdown_tables_as_structured_children(self):
        markdown = '# Metrics\n\n| Name | Value |\n| --- | --- |\n| Latency | 120 ms |'
        nodes = split_evidence_block(
            markdown,
            markdown_start=0,
            markdown_end=len(markdown),
            source_locator={'type': 'text_file'},
            block_id='block-table',
        )
        self.assertEqual([node['node_type'] for node in nodes], ['section', 'table'])
        self.assertEqual(nodes[1]['parent_node_key'], nodes[0]['node_key'])
        self.assertIn('| Latency | 120 ms |', nodes[1]['content'])

    def test_csv_document_heading_is_not_misidentified_as_the_native_table(self):
        markdown = '# report\n\n| Name | Value |\n| --- | --- |\n| A | 1 |'
        nodes = split_evidence_block(
            markdown,
            markdown_start=0,
            markdown_end=len(markdown),
            source_locator={'type': 'csv_table', 'row_count': 2, 'column_count': 2},
            block_id='csv-block',
        )
        self.assertEqual([node['node_type'] for node in nodes], ['section', 'table'])
        self.assertEqual(nodes[0]['locator_json']['type'], 'csv_document')
        self.assertEqual(nodes[1]['locator_json']['type'], 'csv_table')

    def test_keeps_single_unstructured_block_stable(self):
        markdown = 'A single line with no structural boundaries.'
        nodes = split_evidence_block(
            markdown,
            markdown_start=0,
            markdown_end=len(markdown),
            source_locator={'type': 'text_file'},
            block_id='block-3',
        )
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['node_key'], 'block-3')
        self.assertIsNone(nodes[0]['parent_node_key'])
        self.assertEqual(nodes[0]['content'], markdown)


if __name__ == '__main__':
    unittest.main()
