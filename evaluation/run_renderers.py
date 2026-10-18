"""Oráculo de renderizadores e extratores: o motor concorda com o que outros leitores mostram e leem?

O MuPDF é o leitor do motor, mas não é o único. Aqui cada técnica de ocultar texto é medida em leitores
independentes e comparada com a decisão do motor:
  renderizadores  MuPDF (sempre), pdfium (`pip install pypdfium2`, o motor do Chrome) e poppler (`pdftoppm`)
  extratores      MuPDF (sempre), pypdf, pdfminer.six e pdftotext, os que estiverem instalados
Ferramentas ausentes são ignoradas com um aviso.

Duas regras (a segunda está no sentido perigoso: o texto chega à IA por outro caminho):
  1. se o MuPDF mostra o texto e outro renderizador não, o motor precisa ter alertado ou deixado o texto fora do TXT;
  2. se outro extrator lê um texto que a extração do MuPDF não lê, o motor precisa ter alertado.

Origem: a v2.9 afirmou, só pela especificação, que texto com mesclagem `Lighten` some em Chrome e poppler; a
medição mostrou que os três o exibem, e que o divergente de verdade era `Separation /None`. Este script existe para
que a próxima afirmação desse tipo seja medida.

Uso (na raiz do projeto):
    python -m evaluation.run_renderers            # tabela
    python -m evaluation.run_renderers --check    # sai com erro se alguma regra for violada
"""
import shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pymupdf
from engine import analyze_pdf

try: import pypdfium2
except Exception: pypdfium2 = None
try: from pypdf import PdfReader
except Exception: PdfReader = None
try: from pdfminer.high_level import extract_text as miner_text
except Exception: miner_text = None

PAY = 'HIDDENPAYLOAD'
TEXT = f'({PAY} lorem ipsum dolor sit amet) Tj'


def doc_with(content, setup=None):
    doc = pymupdf.open(); page = doc.new_page(width=420, height=300)
    page.insert_text((30, 50), 'Experiencia profissional em engenharia de dados', fontsize=12)
    resources = int(doc.xref_get_key(page.xref, 'Resources')[1].split()[0])
    if setup: setup(doc, page, resources)
    stream = page.get_contents()[0]; doc.update_stream(stream, doc.xref_stream(stream) + content.encode()); return doc


def shown(color='0 g', extra='', pre='', post=''): return f'\n{pre} BT /helv 12 Tf {color} {extra} 30 150 Td {TEXT} ET {post}\n'
def gstate(entry): return lambda doc, page, res: doc.xref_set_key(res, 'ExtGState', f'<</GS0<<{entry}>>>>')


def smask_black(doc, page, res):
    group = doc.get_new_xref(); doc.update_object(group, '<</Type/XObject/Subtype/Form/BBox[0 0 420 300]/Group<</S/Transparency/CS/DeviceGray>>>>')
    doc.update_stream(group, b'0 g 0 0 420 300 re f')
    doc.xref_set_key(res, 'ExtGState', f'<</GS0<</SMask<</Type/Mask/S/Luminosity/G {group} 0 R>>>>>>')


def white_pattern(doc, page, res):
    pattern = doc.get_new_xref()
    doc.update_object(pattern, '<</Type/Pattern/PatternType 1/PaintType 1/TilingType 1/BBox[0 0 10 10]/XStep 10/YStep 10/Resources<<>>>>')
    doc.update_stream(pattern, b'1 g 0 0 10 10 re f'); doc.xref_set_key(res, 'Pattern', f'<</P1 {pattern} 0 R>>')


def empty_form(doc, page, res):
    form = doc.get_new_xref(); doc.update_object(form, '<</Type/XObject/Subtype/Form/BBox[0 0 0 0]/Resources<</Font<</helv 1 0 R>>>>>>')
    doc.update_stream(form, shown().encode()); doc.xref_set_key(res, 'XObject', f'<</Fx {form} 0 R>>')


def optional_layer_off(doc, page, res):
    layer = doc.add_ocg('Oculta', on=False); doc.xref_set_key(res, 'Properties', f'<</OC0 {layer} 0 R>>')


NONE_INK = '<</CS0[/Separation/None/DeviceGray<</FunctionType 2/Domain[0 1]/C0[0]/C1[0]/N 1>>]>>'
VARIANTS = {
    '(controle) texto visível': lambda: doc_with(shown()),
    'mesclagem Lighten (visível)': lambda: doc_with(shown(pre='q /GS0 gs', post='Q'), gstate('/BM/Lighten')),
    'mesclagem Screen (visível)': lambda: doc_with(shown(pre='q /GS0 gs', post='Q'), gstate('/BM/Screen')),
    'alpha 0': lambda: doc_with(shown(pre='q /GS0 gs', post='Q'), gstate('/CA 0/ca 0')),
    'renderização invisível (Tr 3)': lambda: doc_with(shown(extra='3 Tr')),
    'branco sobre branco': lambda: doc_with(shown(color='1 g')),
    'largura zero (Tz 0)': lambda: doc_with(shown(extra='0 Tz')),
    'fonte de 0,001 pt': lambda: doc_with(f'\nBT /helv 0.001 Tf 30 150 Td {TEXT} ET\n'),
    'fora da página': lambda: doc_with(f'\nBT /helv 12 Tf 1 0 0 1 -5000 150 Tm {TEXT} ET\n'),
    'máscara de recorte vazia': lambda: doc_with(shown(pre='q 0 0 1 1 re W n', post='Q')),
    'Form XObject de BBox vazio': lambda: doc_with('\n/Fx Do\n', empty_form),
    'retângulo branco por cima': lambda: doc_with(shown() + '1 g 20 140 380 30 re f\n'),
    'tinta Separation /None': lambda: doc_with(shown(color='/CS0 cs 1 scn'), lambda d, p, r: d.xref_set_key(r, 'ColorSpace', NONE_INK)),
    'camada opcional desligada': lambda: doc_with('\n/OC /OC0 BDC' + shown() + 'EMC\n', optional_layer_off),
    'máscara suave preta (SMask)': lambda: doc_with(shown(pre='q /GS0 gs', post='Q'), smask_black),
    'preenchimento com padrão branco': lambda: doc_with(shown(color='/Pattern cs /P1 scn'), white_pattern),
    'overprint com branco': lambda: doc_with(shown(color='1 g', pre='q /GS0 gs', post='Q'), gstate('/OP true/op true/OPM 1')),
}


def dark_in_text_band(rgb):
    """Há tinta escura na faixa onde o texto de teste é desenhado (baseline em y = 150, de baixo para cima)?"""
    return int(rgb[136:153, 30:400, :3].min()) < 110


def render_all(path, workdir):
    """Quais renderizadores mostram o texto: {nome: bool}. Ausentes não aparecem."""
    shows = {}
    pix = pymupdf.open(path)[0].get_pixmap(dpi=72); shows['MuPDF'] = dark_in_text_band(np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n))
    if pypdfium2 is not None:
        bitmap = pypdfium2.PdfDocument(str(path))[0].render(scale=1).to_numpy(); shows['pdfium'] = dark_in_text_band(bitmap[:, :, [2, 1, 0]])
    if shutil.which('pdftoppm'):
        prefix = workdir / 'poppler'; subprocess.run(['pdftoppm', '-r', '72', '-png', str(path), str(prefix)], check=True, capture_output=True)
        image = next(workdir.glob('poppler*.png')); pm = pymupdf.Pixmap(str(image)); image.unlink()
        shows['poppler'] = dark_in_text_band(np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w, pm.n))
    return shows


def extract_all(path):
    """Quais extratores leem o texto: {nome: bool}. Ausentes não aparecem."""
    reads = {'MuPDF': PAY in pymupdf.open(path)[0].get_text()}
    if PdfReader is not None: reads['pypdf'] = PAY in (PdfReader(str(path)).pages[0].extract_text() or '')
    if miner_text is not None: reads['pdfminer'] = PAY in miner_text(str(path))
    if shutil.which('pdftotext'): reads['pdftotext'] = PAY in subprocess.run(['pdftotext', str(path), '-'], capture_output=True, text=True).stdout
    return reads


def main(check=False):
    renderers = ['MuPDF'] + (['pdfium'] if pypdfium2 else []) + (['poppler'] if shutil.which('pdftoppm') else [])
    missing = [name for name, ok in (('pdfium (pypdfium2)', pypdfium2), ('poppler (pdftoppm)', shutil.which('pdftoppm')), ('pypdf', PdfReader),
                                      ('pdfminer.six', miner_text), ('pdftotext', shutil.which('pdftotext'))) if not ok]
    print('renderizadores:', ', '.join(renderers)); print('ferramentas ausentes (ignoradas):', ', '.join(missing) or 'nenhuma')
    violations = []; workdir = Path(tempfile.mkdtemp()); path = workdir / 'v.pdf'
    print(f'\n{"variante":34} {"vê":20} {"lê":24} motor')
    for name, build in VARIANTS.items():
        doc = build(); doc.save(path); doc.close()
        result = analyze_pdf(path); alerts = sorted({a['type'] for a in result['alerts']}); leaks = PAY in result['text']
        shows, reads = render_all(path, workdir), extract_all(path)
        see = ','.join(k for k, v in shows.items() if v) or '-'; read = ','.join(k for k, v in reads.items() if v) or '-'
        print(f'{name:34} {see:20} {read:24} {",".join(alerts) or "(nenhum)"}{" [no TXT]" if leaks else ""}')
        if shows['MuPDF'] and not all(shows.values()) and not alerts and leaks:
            violations.append(f'{name}: o MuPDF mostra e {[k for k, v in shows.items() if not v]} não; o texto foi para o TXT sem alerta')
        if not reads['MuPDF'] and any(reads.values()) and not alerts:
            violations.append(f'{name}: {[k for k, v in reads.items() if v]} leem um texto que o MuPDF descarta; sem alerta')
    print('\n' + ('Violações:\n  ' + '\n  '.join(violations) if violations else 'Nenhuma violação.'))
    return 1 if (check and violations) else 0


if __name__ == '__main__':
    raise SystemExit(main(check='--check' in sys.argv))
