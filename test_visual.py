"""Análise visual: texto que some conforme o renderizador (modos de mesclagem) e variantes de texto invisível.

O MuPDF compõe a página sobre fundo transparente; Chrome (pdfium) e poppler desenham sobre papel branco. Texto
preto com `/BM /Lighten` (e outros modos) aparece no primeiro e some nos outros. Cada teste usa uma carga neutra,
que nenhum padrão de frase reconhece, para medir só o detector visual.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
from engine import analyze_pdf

PAYLOAD = 'HIDDENPAYLOAD lorem ipsum dolor sit amet consectetur'


def build_pdf(path, content, resources=None):
    """Página com uma linha visível e `content` acrescentado ao fluxo de conteúdo."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=300)
        page.insert_text((30, 50), 'Experiencia profissional em engenharia de dados', fontsize=12)
        if resources: resources(doc, int(doc.xref_get_key(page.xref, 'Resources')[1].split()[0]))
        ref = page.get_contents()[0]; doc.update_stream(ref, doc.xref_stream(ref) + content.encode())
        doc.save(path)


def blend_pdf(path, mode, gray=0):
    build_pdf(path, f'\nq /GS0 gs BT /helv 12 Tf {gray} g 30 150 Td ({PAYLOAD}) Tj ET Q\n',
              lambda doc, res: doc.xref_set_key(res, 'ExtGState', f'<</GS0<</BM/{mode}>>>>'))


class BlendModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path = Path(self.tmp.name) / 'b.pdf'

    def analyse(self, mode, gray=0):
        blend_pdf(self.path, mode, gray); return analyze_pdf(self.path)

    def test_black_text_that_vanishes_on_white_paper_is_flagged_and_kept_out_of_the_txt(self):
        """Antes: sem alerta e o texto oculto ia para o TXT liberado (o MuPDF o mostra preto)."""
        for mode in ('Lighten', 'Screen', 'Overlay', 'ColorDodge', 'ColorBurn', 'SoftLight', 'Difference', 'Exclusion'):
            with self.subTest(mode):
                result = self.analyse(mode)
                self.assertIn('baixo_contraste', {a['type'] for a in result['alerts']})
                self.assertNotIn('HIDDENPAYLOAD', result['text'])

    def test_legitimate_blend_modes_with_visible_black_text_raise_no_alert(self):
        """Guarda contra falso positivo: Multiply e Darken são usados de verdade e o texto continua visível."""
        for mode in ('Normal', 'Multiply', 'Darken', 'HardLight'):
            with self.subTest(mode):
                result = self.analyse(mode)
                self.assertEqual(result['alerts'], [])
                self.assertIn('HIDDENPAYLOAD', result['text'])

    def test_explanation_names_the_renderer_difference(self):
        details = [a['detail'] for a in self.analyse('Lighten')['alerts'] if a['type'] == 'baixo_contraste']
        self.assertTrue(any('papel branco' in d for d in details), details)

    def test_pages_without_blend_modes_do_not_pay_for_the_second_render(self):
        build_pdf(self.path, f'\nBT /helv 12 Tf 0 g 30 150 Td ({PAYLOAD}) Tj ET\n')
        with patch('engine.paper_white_renders', side_effect=AssertionError('não deveria renderizar de novo')) as second:
            result = analyze_pdf(self.path)
        second.assert_not_called(); self.assertEqual(result['alerts'], [])

    def test_failure_of_the_second_render_falls_back_to_the_normal_analysis(self):
        blend_pdf(self.path, 'Multiply')
        with patch('engine.paper_white_renders', return_value=(None, None)):
            result = analyze_pdf(self.path)
        self.assertEqual(result['alerts'], []); self.assertIn('HIDDENPAYLOAD', result['text'])   # sem a 2ª renderização, vale a análise de sempre

    def test_blend_mode_array_form_is_detected(self):
        build_pdf(self.path, f'\nq /GS0 gs BT /helv 12 Tf 0 g 30 150 Td ({PAYLOAD}) Tj ET Q\n',
                  lambda doc, res: doc.xref_set_key(res, 'ExtGState', '<</GS0<</BM[/Lighten/Normal]>>>>'))
        self.assertIn('baixo_contraste', {a['type'] for a in analyze_pdf(self.path)['alerts']})


class InvisibleVariantTests(unittest.TestCase):
    """Variantes de texto invisível: nenhuma pode levar o texto oculto ao TXT, mesmo sem frase suspeita."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path = Path(self.tmp.name) / 'v.pdf'

    def check(self, content, resources=None):
        build_pdf(self.path, content, resources); result = analyze_pdf(self.path)
        self.assertNotIn('HIDDENPAYLOAD', result['text']); return {a['type'] for a in result['alerts']}

    def test_text_operators_that_hide_text_are_flagged(self):
        casos = {
            'largura zero (Tz 0)': (f'\nBT /helv 12 Tf 0 Tz 30 150 Td ({PAYLOAD}) Tj ET\n', {'fora_da_pagina'}),
            'espaçamento enorme (Tc)': (f'\nBT /helv 12 Tf 5000 Tc 30 150 Td ({PAYLOAD}) Tj ET\n', {'fora_da_pagina'}),
            'renderização invisível (Tr 3)': (f'\nBT /helv 12 Tf 3 Tr 30 150 Td ({PAYLOAD}) Tj ET\n', {'texto_invisivel'}),
            'fonte minúscula': (f'\nBT /helv 0.001 Tf 30 150 Td ({PAYLOAD}) Tj ET\n', {'fonte_pequena'}),
            'branco sobre branco': (f'\nBT /helv 12 Tf 1 g 30 150 Td ({PAYLOAD}) Tj ET\n', {'baixo_contraste'}),
            'fora da página': (f'\nBT /helv 12 Tf 1 0 0 1 -5000 150 Tm ({PAYLOAD}) Tj ET\n', {'fora_da_pagina'}),
            'retângulo branco por cima': (f'\nBT /helv 12 Tf 0 g 30 150 Td ({PAYLOAD}) Tj ET 1 g 20 140 380 30 re f\n', {'possivel_sobreposicao'}),
        }
        for nome, (content, esperado) in casos.items():
            with self.subTest(nome): self.assertTrue(esperado & self.check(content), nome)

    def test_clipped_away_text_never_reaches_the_txt(self):
        self.check(f'\nq 0 0 1 1 re W n BT /helv 12 Tf 0 g 30 150 Td ({PAYLOAD}) Tj ET Q\n')   # clip vazio: o MuPDF não o extrai


if __name__ == '__main__': unittest.main()
