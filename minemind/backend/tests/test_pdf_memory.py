"""Exercise actual PDF parsing without loading the optional layout model."""
from unittest.mock import patch

import pymupdf

from services.parser import parse_pdf


def test_ruled_table_and_text_extract_without_layout_inference(tmp_path):
    target = tmp_path / 'equipment.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        for y in (50, 80, 110):
            page.draw_line((50, y), (350, y))
        for x in (50, 200, 350):
            page.draw_line((x, 50), (x, 110))
        for point, text in [((60, 70), 'Equipment'), ((210, 70), 'Pressure'),
                            ((60, 100), 'Pump'), ((210, 100), '42 kPa')]:
            page.insert_text(point, text)
        doc.save(target)
    with patch.object(pymupdf.Page, 'get_layout', side_effect=AssertionError('Layout model must not run')):
        result = parse_pdf(str(target))
    assert '[PDF page 1]' in result
    assert 'Equipment | Pressure' in result
    assert 'Pump | 42 kPa' in result
