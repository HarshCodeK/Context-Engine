import io
import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
import context_studio.api as api_module
import context_studio.documents as documents_module
from context_studio.api import _allow_upload
from context_studio.settings import _positive_int_env
from context_studio.documents import extract_document
from docx import Document
from openpyxl import Workbook
from pptx import Presentation


class ExtractionTests(unittest.TestCase):
    def test_text_evidence_schema_has_stable_source_and_block_ids(self):
        source = b"# Notes\n\nA reliable source block."
        first = extract_document('notes.md', source)
        renamed = extract_document('renamed.md', source)
        evidence = first['evidence']
        self.assertEqual(evidence['schema_version'], '1.0')
        self.assertEqual(evidence['source_id'], hashlib.sha256(source).hexdigest())
        self.assertEqual(evidence['source_id'], renamed['evidence']['source_id'])
        self.assertEqual(evidence['blocks'][0]['block_id'], renamed['evidence']['blocks'][0]['block_id'])
        block = evidence['blocks'][0]
        self.assertEqual(block['locator'], {'type': 'text_file'})
        self.assertEqual(block['content_sha256'], hashlib.sha256(first['markdown'].encode('utf-8')).hexdigest())
        self.assertEqual(block['markdown_range']['end'], len(first['markdown']))
        self.assertEqual(block['markdown_range']['unit'], 'unicode_code_points')

    def test_csv_exposes_stable_native_headers_and_logical_record_coordinates(self):
        source = 'Name,Name,Notes\nAsha,,"Line one\nLine two"\nZoë,Owner,"quoted, value"\n'.encode('utf-8')
        result = extract_document('people.csv', source)
        table = result['evidence']['tables'][0]
        self.assertEqual([header['label'] for header in table['headers']], ['Name', 'Name (2)', 'Notes'])
        self.assertEqual([header['column_label'] for header in table['headers']], ['A', 'B', 'C'])
        self.assertEqual(table['rows'][0]['row_number'], 2)
        self.assertEqual(table['rows'][0]['cells'][1]['value'], '')
        self.assertTrue(table['rows'][0]['cells'][1]['is_empty'])
        self.assertEqual(table['rows'][0]['cells'][2]['value'], 'Line one\nLine two')
        self.assertEqual(table['rows'][1]['cells'][0]['value'], 'Zoë')
        self.assertEqual(table['rows'][1]['cells'][2]['value'], 'quoted, value')
        self.assertEqual(table['table_key'], extract_document('renamed.csv', source)['evidence']['tables'][0]['table_key'])

    def test_csv_native_cell_index_cap_keeps_markdown_table_and_surfaces_warning(self):
        source = b'Name,Value\nA,100\nB,200\n'
        with patch.object(documents_module, 'MAX_NATIVE_TABLE_CELLS', 2):
            result = extract_document('bounded.csv', source)
        table = result['evidence']['tables'][0]
        self.assertEqual(table['indexed_cell_count'], 2)
        self.assertTrue(table['cells_truncated'])
        self.assertTrue(table['locator']['cells_truncated'])
        self.assertIn('B', result['markdown'])
        self.assertIn('200', result['markdown'])
        self.assertTrue(any('Native CSV cell indexing capped' in warning for warning in result['warnings']))

    def test_csv_detects_semicolon_delimiter_without_splitting_quoted_commas(self):
        source = 'Name;Notes\nAsha;"Planning, research and delivery"\nRavi;"Line one\nLine two"\n'.encode('utf-8')
        result = extract_document('semicolon.csv', source)
        table = result['evidence']['tables'][0]
        self.assertEqual(table['locator']['delimiter'], ';')
        self.assertEqual(table['headers'][1]['value'], 'Notes')
        self.assertEqual(table['rows'][0]['cells'][1]['value'], 'Planning, research and delivery')
        self.assertEqual(table['rows'][1]['cells'][1]['value'], 'Line one\nLine two')

    def test_pdf_evidence_blocks_anchor_each_page_to_markdown_ranges(self):
        document = fitz.open()
        first_page = document.new_page()
        first_page.insert_text((72, 72), 'First evidence page')
        second_page = document.new_page()
        second_page.insert_text((72, 72), 'Second evidence page')
        content = document.tobytes()
        document.close()
        result = extract_document('pages.pdf', content)
        blocks = result['evidence']['blocks']
        self.assertEqual([block['locator'] for block in blocks], [
            {'type': 'pdf_page', 'page': 1}, {'type': 'pdf_page', 'page': 2},
        ])
        for block, expected in zip(blocks, ('First evidence page', 'Second evidence page')):
            span = block['markdown_range']
            self.assertIn(expected, result['markdown'][span['start']:span['end']])
            self.assertEqual(block['source_id'], result['evidence']['source_id'])

    def test_office_evidence_uses_native_paragraph_slide_and_sheet_locators(self):
        document = Document()
        document.add_heading('Project brief', level=1)
        document.add_paragraph('A paragraph with a traceable source position.')
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text = 'Key'
        table.cell(0, 1).text = 'Value'
        table.cell(1, 0).text = 'A'
        table.cell(1, 1).text = 'B'
        word_bytes = io.BytesIO()
        document.save(word_bytes)
        word_result = extract_document('brief.docx', word_bytes.getvalue())
        word_locators = [block['locator']['type'] for block in word_result['evidence']['blocks']]
        self.assertIn('docx_paragraph', word_locators)
        self.assertIn('docx_table', word_locators)
        for block in word_result['evidence']['blocks']:
            span = block['markdown_range']
            self.assertTrue(word_result['markdown'][span['start']:span['end']])

        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(0, 0, 100, 100).text = 'A slide statement'
        pptx_bytes = io.BytesIO()
        deck.save(pptx_bytes)
        slide_result = extract_document('brief.pptx', pptx_bytes.getvalue())
        self.assertTrue(any(block['locator'].get('type') == 'pptx_shape' and block['locator'].get('slide') == 1 for block in slide_result['evidence']['blocks']))
        for block in slide_result['evidence']['blocks']:
            span = block['markdown_range']
            self.assertTrue(slide_result['markdown'][span['start']:span['end']])

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Budget'
        sheet.append(['Item', 'Cost'])
        sheet.append(['Hosting', 12])
        xlsx_bytes = io.BytesIO()
        workbook.save(xlsx_bytes)
        sheet_result = extract_document('budget.xlsx', xlsx_bytes.getvalue())
        self.assertTrue(any(block['locator'].get('type') == 'xlsx_range' and block['locator'].get('sheet') == 'Budget' for block in sheet_result['evidence']['blocks']))
        for block in sheet_result['evidence']['blocks']:
            span = block['markdown_range']
            self.assertTrue(sheet_result['markdown'][span['start']:span['end']])

    def test_pdf_ocr_calls_respect_remaining_file_deadline(self):
        document = fitz.open()
        document.new_page()
        document.new_page()
        content = document.tobytes()
        document.close()
        timeouts = []

        def fake_ocr(image, timeout_seconds=None, deadline=None):
            timeouts.append(timeout_seconds)
            return 'Recognized page text'

        with patch.object(documents_module, '_ocr_available', return_value=True), \
             patch.object(documents_module, 'MAX_OCR_TOTAL_SECONDS', 1.0), \
             patch.object(documents_module, 'MAX_OCR_PAGES_PER_FILE', 2), \
             patch.object(documents_module, 'MAX_OCR_SECONDS', 12), \
             patch.object(documents_module, 'ocr_image', side_effect=fake_ocr):
            result = extract_document('scanned.pdf', content, 'application/pdf')

        self.assertEqual(result['pages'], 2)
        self.assertTrue(timeouts)
        self.assertTrue(all(timeout is not None and 0 < timeout <= 1.0 for timeout in timeouts))

    def test_upload_limit_environment_values_must_be_positive_integers(self):
        for value in ("0", "-1", "not-a-number", "1.5"):
            with self.subTest(value=value), patch.dict(os.environ, {"TEST_UPLOAD_LIMIT": value}):
                with self.assertRaisesRegex(RuntimeError, "TEST_UPLOAD_LIMIT must be a positive integer"):
                    _positive_int_env("TEST_UPLOAD_LIMIT", 10)

    def test_upload_rate_limit_tracking_is_bounded_by_client_count(self):
        api_module._request_times.clear()
        with patch.object(api_module, "MAX_TRACKED_CLIENTS", 2), patch.object(api_module, "RATE_LIMIT", 1):
            self.assertTrue(_allow_upload("client-a", 1.0))
            self.assertTrue(_allow_upload("client-b", 1.0))
            self.assertTrue(_allow_upload("client-c", 1.0))
            self.assertEqual(list(api_module._request_times), ["client-b", "client-c"])
            self.assertFalse(_allow_upload("client-c", 2.0))
            self.assertTrue(_allow_upload("client-c", 62.1))

    def test_text_wraps_content(self):
        result = extract_document('brief.txt', b'Hello\nworld')
        self.assertIn('# brief', result['markdown'])
        self.assertIn('Hello', result['markdown'])

    def test_markdown_is_preserved(self):
        source = '# Keep heading\n\n- one\n- two'
        self.assertEqual(extract_document('notes.md', source.encode())['markdown'], source)

    def test_json_pretty_prints_and_rejects_invalid(self):
        result = extract_document('data.json', b'{"a":1}')
        self.assertIn('"a": 1', result['markdown'])
        with self.assertRaisesRegex(ValueError, 'Invalid JSON'):
            extract_document('bad.json', b'{')

    def test_csv_becomes_markdown_table(self):
        result = extract_document('people.csv', b'name,role\nAda,Engineer')
        self.assertIn('| name | role |', result['markdown'])
        self.assertIn('| Ada | Engineer |', result['markdown'])

    def test_csv_accepts_common_windows_browser_mime_type(self):
        result = extract_document('people.csv', b'name,role\nAda,Engineer', 'application/vnd.ms-excel')
        self.assertIn('| Ada | Engineer |', result['markdown'])

    def test_long_form_fixture_corpus_covers_every_non_image_format(self):
        fixture_dir = Path(__file__).resolve().parents[1] / 'examples' / 'fixtures'
        expected = {
            'northstar-programme.txt', 'northstar-programme.md', 'northstar-programme.markdown',
            'northstar-programme.pdf', 'northstar-programme.docx', 'northstar-programme.pptx',
            'northstar-programme.xlsx', 'site-performance.csv', 'site-register.json',
            'programme-handbook.html',
        }
        self.assertTrue(all((fixture_dir / name).is_file() for name in expected))
        for filename in sorted(expected):
            with self.subTest(filename=filename):
                result = extract_document(filename, (fixture_dir / filename).read_bytes())
                self.assertGreater(result['words'], 500)
                self.assertTrue(result['markdown'].strip())
                self.assertEqual(result['processing']['external_model_calls'], 0)

    def test_html_scripts_are_omitted(self):
        result = extract_document('page.html', b'<h1>Hello</h1><script>secret()</script><p>World</p>')
        self.assertIn('Hello', result['markdown'])
        self.assertIn('World', result['markdown'])
        self.assertNotIn('secret', result['markdown'])

    def test_docx_paragraph_and_table(self):
        doc = Document(); doc.add_heading('Summary', level=1); doc.add_paragraph('Important')
        table = doc.add_table(rows=2, cols=2); table.cell(0,0).text='Key'; table.cell(0,1).text='Value'; table.cell(1,0).text='A'; table.cell(1,1).text='B'
        stream=io.BytesIO(); doc.save(stream)
        result=extract_document('notes.docx',stream.getvalue())
        self.assertIn('# Summary', result['markdown']); self.assertIn('| Key | Value |',result['markdown'])

    def test_xlsx_sheet_and_rows(self):
        wb=Workbook(); ws=wb.active; ws.title='Costs'; ws.append(['Item','Cost']); ws.append(['Hosting',12])
        stream=io.BytesIO(); wb.save(stream)
        result=extract_document('budget.xlsx',stream.getvalue())
        self.assertIn('## Sheet: Costs',result['markdown']); self.assertIn('| Hosting | 12 |',result['markdown'])

    def test_pptx_slide_text(self):
        deck=Presentation(); slide=deck.slides.add_slide(deck.slide_layouts[5]); slide.shapes.title.text='Launch'
        stream=io.BytesIO(); deck.save(stream)
        result=extract_document('pitch.pptx',stream.getvalue())
        self.assertIn('## Slide 1',result['markdown']); self.assertIn('Launch',result['markdown'])

    def test_unsupported_extension(self):
        with self.assertRaises(ValueError): extract_document('payload.exe',b'x')

    def test_empty_file_is_rejected_with_actionable_error(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            extract_document('empty.txt', b'')

    def test_extension_does_not_override_pdf_signature(self):
        with self.assertRaisesRegex(ValueError, 'signature'):
            extract_document('notes.pdf', b'This is not a PDF')

    def test_claimed_mime_type_must_match_extension(self):
        with self.assertRaisesRegex(ValueError, 'does not match'):
            extract_document('notes.pdf', b'%PDF-1.7\n', 'text/plain')

    def test_generic_mime_type_is_checked_against_actual_signature(self):
        with self.assertRaisesRegex(ValueError, 'signature'):
            extract_document('notes.pdf', b'not a pdf', 'application/octet-stream')

    def test_office_archive_must_contain_expected_document_parts(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('random.txt', 'not a Word document')
        with self.assertRaisesRegex(ValueError, 'does not look like a valid DOCX'):
            extract_document('fake.docx', stream.getvalue())

    def test_corrupt_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Invalid or corrupt image'):
            extract_document('fake.png', b'not a png')

    def test_image_without_ocr_has_explicit_limitation(self):
        from PIL import Image
        image = Image.new('RGB', (8, 8), 'white')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        with patch.object(documents_module, '_tesseract_executable', return_value=None):
            result = extract_document('scan.png', stream.getvalue(), 'image/png')
        self.assertTrue(any('OCR is unavailable' in warning for warning in result['warnings']))
        self.assertIn('No text could be extracted', result['markdown'])
        self.assertEqual(result['processing']['route'], 'image_metadata')
        self.assertEqual(result['processing']['external_model_calls'], 0)

    def test_ocr_uses_tesseract_cli_without_a_python_wrapper(self):
        from PIL import Image
        image = Image.new('RGB', (8, 8), 'white')
        completed = documents_module.subprocess.CompletedProcess(args=['tesseract'], returncode=0, stdout=b'  Recognized text\n', stderr=b'')
        with patch.object(documents_module, '_tesseract_executable', return_value='tesseract.exe'), \
             patch.object(documents_module.subprocess, 'run', return_value=completed) as run:
            result = documents_module.ocr_image(image, timeout_seconds=2)
        self.assertEqual(result, 'Recognized text')
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['tesseract.exe', 'stdin', 'stdout', '-l', 'eng'])
        self.assertTrue(kwargs['input'].startswith(b'\x89PNG'))
        self.assertEqual(kwargs['timeout'], 2)
        self.assertFalse(kwargs['check'])

    def test_tesseract_executable_resolves_configured_path_and_path_command(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'tesseract custom.exe'
            executable.write_bytes(b'placeholder')
            with patch.dict(documents_module.os.environ, {'TESSERACT_CMD': str(executable)}):
                self.assertEqual(documents_module._tesseract_executable(), str(executable))

        with patch.dict(documents_module.os.environ, {'TESSERACT_CMD': 'tesseract'}), \
             patch.object(documents_module.shutil, 'which', return_value=r'C:\Tools\Tesseract\tesseract.exe') as which:
            self.assertEqual(documents_module._tesseract_executable(), r'C:\Tools\Tesseract\tesseract.exe')
            which.assert_called_once_with('tesseract')

        with patch.dict(documents_module.os.environ, {'TESSERACT_CMD': ''}):
            self.assertIsNone(documents_module._tesseract_executable())

    def test_ocr_process_failure_does_not_expose_stderr(self):
        from PIL import Image
        failed = documents_module.subprocess.CompletedProcess(
            args=['tesseract'], returncode=1, stdout=b'', stderr=b'private machine path'
        )
        with patch.object(documents_module, '_tesseract_executable', return_value='tesseract.exe'), \
             patch.object(documents_module.subprocess, 'run', return_value=failed):
            with self.assertRaisesRegex(RuntimeError, 'Tesseract could not process this image') as error:
                documents_module.ocr_image(Image.new('RGB', (8, 8), 'white'), timeout_seconds=1)
        self.assertNotIn('private machine path', str(error.exception))

    def test_ocr_cli_timeout_becomes_actionable_timeout_error(self):
        from PIL import Image
        with patch.object(documents_module, '_tesseract_executable', return_value='tesseract.exe'), \
             patch.object(documents_module.subprocess, 'run', side_effect=documents_module.subprocess.TimeoutExpired('tesseract.exe', 1)):
            with self.assertRaisesRegex(TimeoutError, 'exceeded its time budget'):
                documents_module.ocr_image(Image.new('RGB', (8, 8), 'white'), timeout_seconds=1)

    def test_pdf_encrypted_document_is_rejected(self):
        import pymupdf as fitz
        stream = io.BytesIO()
        doc = fitz.open()
        doc.new_page()
        doc.save(stream, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='reader')
        doc.close()
        with self.assertRaisesRegex(ValueError, 'password-protected'):
            extract_document('locked.pdf', stream.getvalue())

    def test_pdf_with_no_text_layer_reports_scanned_page(self):
        import pymupdf as fitz
        stream = io.BytesIO()
        doc = fitz.open()
        doc.new_page()
        doc.save(stream)
        doc.close()
        with patch.object(documents_module, '_tesseract_executable', return_value=None):
            result = extract_document('scan.pdf', stream.getvalue(), 'application/pdf')
        self.assertTrue(any('no readable text' in warning for warning in result['warnings']))
        self.assertIn('No selectable text found', result['markdown'])

    def test_corrupt_office_archive_is_rejected_cleanly(self):
        with self.assertRaisesRegex(ValueError, 'Invalid Office document archive'):
            extract_document('broken.docx', b'not a zip archive')

    def test_extreme_office_compression_ratio_is_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('word/document.xml', 'A' * (2 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, 'compression ratio'):
            extract_document('suspicious.docx', stream.getvalue())

    def test_size_limit(self):
        with self.assertRaises(ValueError): extract_document('large.txt',b'x'*(20*1024*1024+1))


if __name__ == '__main__': unittest.main()
