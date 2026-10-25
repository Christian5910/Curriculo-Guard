"""Análise visual: texto que some conforme o leitor, texto recortado e variantes de texto invisível.

Cada teste usa uma carga neutra, que nenhum padrão de frase reconhece, para medir só o detector visual.

Nota histórica: a v2.9 afirmou que texto preto com modo de mesclagem `Lighten` some em Chrome e poppler. Medindo
com pdfium e poppler (evaluation/run_renderers.py) isso é falso: os três renderizadores o mostram. Esse recurso foi
removido na v2.10, e `VisibleBlendModeTests` garante que o texto visível volta a ir para o TXT.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pymupdf
from curriculo_guard import engine
from curriculo_guard.engine import analyze_pdf, dropped_letters, mupdf_only_ink, reference_render, validate_params

PAYLOAD = 'HIDDENPAYLOAD lorem ipsum dolor sit amet consectetur'
HAS_PDFIUM = engine._pdfium is not None


def build_pdf(path, content, resources=None):
    """Página com uma linha visível e `content` acrescentado ao fluxo de conteúdo."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=300)
        page.insert_text((30, 50), 'Experiencia profissional em engenharia de dados', fontsize=12)
        if resources: resources(doc, int(doc.xref_get_key(page.xref, 'Resources')[1].split()[0]))
        ref = page.get_contents()[0]; doc.update_stream(ref, doc.xref_stream(ref) + content.encode())
        doc.save(path)


def shown(color='0 g', extra='', pre='', post=''):
    return f'\n{pre} BT /helv 12 Tf {color} {extra} 30 150 Td ({PAYLOAD}) Tj ET {post}\n'


def colorspace(spec):
    return lambda doc, res: doc.xref_set_key(res, 'ColorSpace', f'<</CS0{spec}>>')


NONE_INK = '[/Separation/None/DeviceGray<</FunctionType 2/Domain[0 1]/C0[0]/C1[0]/N 1>>]'
PANTONE = '[/Separation/PANTONE#20287#20C/DeviceGray<</FunctionType 2/Domain[0 1]/C0[1]/C1[0]/N 1>>]'   # tinta de verdade: 1 = preto


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path = Path(self.tmp.name) / 'v.pdf'

    def analyse(self, content, resources=None, **options):
        build_pdf(self.path, content, resources); return analyze_pdf(self.path, **options)

    def types(self, result): return {a['type'] for a in result['alerts']}


class VisibleBlendModeTests(Base):
    def test_black_text_with_any_blend_mode_stays_in_the_txt_without_alert(self):
        """Medido com MuPDF, pdfium e poppler: o texto preto é visível com todos estes modos."""
        for mode in ('Normal', 'Multiply', 'Darken', 'HardLight', 'Lighten', 'Screen', 'Overlay', 'ColorDodge', 'Difference', 'Exclusion'):
            with self.subTest(mode):
                result = self.analyse(shown(pre='q /GS0 gs', post='Q'), lambda doc, res, m=mode: doc.xref_set_key(res, 'ExtGState', f'<</GS0<</BM/{m}>>>>'))
                self.assertEqual(result['alerts'], []); self.assertIn('HIDDENPAYLOAD', result['text'])


class ClippedTextTests(Base):
    """Texto desenhado que a extração do MuPDF descarta, mas que pypdf, pdfminer e pdftotext leem no PDF original."""

    def empty_form(self, doc, res):
        x = doc.get_new_xref(); doc.update_object(x, '<</Type/XObject/Subtype/Form/BBox[0 0 0 0]/Resources<</Font<</helv 1 0 R>>>>>>')
        doc.update_stream(x, shown().encode()); doc.xref_set_key(res, 'XObject', f'<</Fx {x} 0 R>>')

    def test_text_clipped_away_is_flagged(self):
        casos = {
            'máscara de recorte vazia': (shown(pre='q 0 0 1 1 re W n', post='Q'), None),
            'Form XObject de BBox vazio': ('\n/Fx Do\n', self.empty_form),
            'fora da página': (f'\nBT /helv 12 Tf 1 0 0 1 -5000 150 Tm ({PAYLOAD}) Tj ET\n', None),
        }
        for nome, (content, resources) in casos.items():
            with self.subTest(nome):
                result = self.analyse(content, resources)
                self.assertIn('texto_recortado', self.types(result)); self.assertNotIn('HIDDENPAYLOAD', result['text'])

    def test_legitimate_double_drawing_is_not_flagged(self):
        """Guarda contra falso positivo: preenchimento + contorno (Tr 2) registra cada letra duas vezes no texttrace."""
        self.assertNotIn('texto_recortado', self.types(self.analyse(shown(extra='2 Tr 0.3 w'))))
        with pymupdf.open() as doc:   # negrito sintético: o mesmo texto desenhado duas vezes, 0,4 pt deslocado
            page = doc.new_page(width=420, height=300)
            for dx in (0, 0.4): page.insert_text((30 + dx, 100), 'Experiencia profissional em engenharia de dados e analise', fontsize=12)
            doc.save(self.path)
        self.assertEqual(analyze_pdf(self.path)['alerts'], [])

    def test_plain_visible_text_is_not_flagged(self):
        self.assertEqual(self.analyse(shown())['alerts'], [])

    def test_dropped_letters_counts_only_what_is_missing(self):
        self.assertEqual(dropped_letters('abc def', 'abc'), 3)
        self.assertEqual(dropped_letters('Olá mundo', 'ola MUNDO'), 1)     # "á" e "a" são letras diferentes
        self.assertEqual(dropped_letters('office', 'oﬃce'), 0)             # ligadura normalizada (NFKC)
        self.assertEqual(dropped_letters('aaa', 'aaaa'), 0)                # só conta o que foi desenhado e não extraído


class NoMarkColorTests(Base):
    def test_separation_none_is_flagged_without_any_extra_dependency(self):
        devicen = '[/DeviceN[/None/None]/DeviceGray<</FunctionType 2/Domain[0 1]/C0[0]/C1[0]/N 1>>]'
        for nome, spec in (('Separation /None', NONE_INK), ('DeviceN só com None', devicen)):
            with self.subTest(nome):
                result = self.analyse(shown(color='/CS0 cs 1 scn'), colorspace(spec), cross_render='off')
                self.assertIn('cor_sem_marca', self.types(result))

    def test_a_real_spot_ink_is_not_flagged(self):
        result = self.analyse(shown(color='/CS0 cs 1 scn'), colorspace(PANTONE), cross_render='off')
        self.assertEqual(result['alerts'], []); self.assertIn('HIDDENPAYLOAD', result['text'])


@unittest.skipUnless(HAS_PDFIUM, 'pypdfium2 não instalado (segunda opinião é opcional)')
class SecondOpinionTests(Base):
    def divergent(self, **options):
        return self.analyse(shown(color='/CS0 cs 1 scn'), colorspace(NONE_INK), **options)

    def test_text_that_mupdf_draws_and_pdfium_does_not_is_flagged_and_kept_out_of_the_txt(self):
        """Antes: o MuPDF desenha o texto de `Separation /None`, pdfium e poppler não, e ele ia para o TXT sem alerta."""
        for mode in ('auto', 'always'):
            with self.subTest(mode):
                result = self.divergent(cross_render=mode)
                self.assertIn('renderizadores_divergem', self.types(result)); self.assertNotIn('HIDDENPAYLOAD', result['text'])
                self.assertEqual(result['metrics']['renderers'], 'mupdf+pdfium')

    def test_off_disables_the_second_opinion(self):
        result = self.divergent(cross_render='off')
        self.assertNotIn('renderizadores_divergem', self.types(result)); self.assertEqual(result['metrics']['renderers'], 'mupdf')
        self.assertIn('cor_sem_marca', self.types(result))   # a checagem estrutural continua valendo, sem dependências

    def test_auto_does_not_pay_for_plain_documents_but_always_does(self):
        build_pdf(self.path, shown())
        # Conta as aberturas em vez de levantar erro: o motor captura qualquer exceção ao abrir o pdfium (degrada com segurança).
        with patch.object(engine._pdfium, 'PdfDocument', wraps=engine._pdfium.PdfDocument) as opened:
            self.assertEqual(analyze_pdf(self.path, cross_render='auto')['metrics']['renderers'], 'mupdf'); opened.assert_not_called()
            self.assertEqual(analyze_pdf(self.path, cross_render='always')['metrics']['renderers'], 'mupdf+pdfium'); opened.assert_called_once()
        with patch.object(engine._pdfium, 'PdfDocument', wraps=engine._pdfium.PdfDocument) as opened:   # PDF com cor Separation: o modo auto abre
            self.analyse(shown(color='/CS0 cs 1 scn'), colorspace(PANTONE), cross_render='auto'); opened.assert_called_once()

    def test_legitimate_pages_with_exotic_features_raise_no_divergence(self):
        """Guarda contra falso positivo: tinta direta real e degradê (sombreado) são vistos pelos dois leitores."""
        result = self.analyse(shown(color='/CS0 cs 1 scn'), colorspace(PANTONE), cross_render='always')
        self.assertNotIn('renderizadores_divergem', self.types(result)); self.assertIn('HIDDENPAYLOAD', result['text'])
        def shading(doc, res):
            doc.xref_set_key(res, 'Shading', '<</Sh0<</ShadingType 2/ColorSpace/DeviceRGB/Coords[0 0 420 0]/Function<</FunctionType 2/Domain[0 1]/C0[0.9 0.9 1]/C1[1 1 0.8]/N 1>>>>>>')
        result = self.analyse('\nq 0 0 420 300 re W n /Sh0 sh Q' + shown(), shading, cross_render='always')
        self.assertNotIn('renderizadores_divergem', self.types(result)); self.assertIn('HIDDENPAYLOAD', result['text'])

    def test_invalid_cross_render_value_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'cross_render'): validate_params({'root': 'x', 'analysis_options': {'cross_render': 'talvez'}})
        validate_params({'root': 'x', 'analysis_options': {'cross_render': 'always'}})


class SecondOpinionHelperTests(unittest.TestCase):
    def test_mupdf_only_ink_needs_strong_ink_in_one_and_a_flat_region_in_the_other(self):
        ink = np.full((100, 100), 255.0); ink[40:50, 10:90] = 0
        flat = np.full((100, 100), 255.0)
        self.assertTrue(mupdf_only_ink(ink, flat, (10, 38, 90, 52), 1.0))
        self.assertFalse(mupdf_only_ink(ink, ink, (10, 38, 90, 52), 1.0))      # os dois desenham
        self.assertFalse(mupdf_only_ink(flat, ink, (10, 38, 90, 52), 1.0))     # só o pdfium desenha: o MuPDF já trata como sem tinta
        photo = np.random.default_rng(1).uniform(0, 255, (100, 100))
        self.assertFalse(mupdf_only_ink(ink, photo, (10, 38, 90, 52), 1.0))    # fundo com variação própria: não é julgado
        self.assertFalse(mupdf_only_ink(ink, flat, (500, 500, 600, 600), 1.0)) # região fora da imagem

    def test_reference_render_degrades_to_none(self):
        self.assertIsNone(reference_render(None, 0, 150, (100, 100, 3)))
        class Broken:
            def __getitem__(self, index): raise RuntimeError('falhou')
        self.assertIsNone(reference_render(Broken(), 0, 150, (100, 100, 3)))


class InvisibleVariantTests(Base):
    """Variantes de texto invisível: nenhuma pode levar o texto oculto ao TXT, mesmo sem frase suspeita."""

    def check(self, content, resources=None):
        result = self.analyse(content, resources); self.assertNotIn('HIDDENPAYLOAD', result['text']); return self.types(result)

    def test_text_operators_that_hide_text_are_flagged(self):
        casos = {
            'largura zero (Tz 0)': (shown(extra='0 Tz'), {'fora_da_pagina'}),
            'espaçamento enorme (Tc)': (shown(extra='5000 Tc'), {'fora_da_pagina'}),
            'renderização invisível (Tr 3)': (shown(extra='3 Tr'), {'texto_invisivel'}),
            'fonte minúscula': (f'\nBT /helv 0.001 Tf 30 150 Td ({PAYLOAD}) Tj ET\n', {'fonte_pequena'}),
            'branco sobre branco': (shown(color='1 g'), {'baixo_contraste'}),
            'fora da página': (f'\nBT /helv 12 Tf 1 0 0 1 -5000 150 Tm ({PAYLOAD}) Tj ET\n', {'fora_da_pagina'}),
            'retângulo branco por cima': (shown() + '1 g 20 140 380 30 re f\n', {'possivel_sobreposicao'}),
        }
        for nome, (content, esperado) in casos.items():
            with self.subTest(nome): self.assertTrue(esperado & self.check(content), nome)


if __name__ == '__main__': unittest.main()
