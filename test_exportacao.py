"""Leitura de relatórios grandes e exportação CSV (inclusive para o Excel em português)."""
import csv
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from workflow import ReviewStore, MAX_REPORT_BYTES


def write_report(folder, name, **extra):
    data = {'status': 'aprovados', 'original_name': name, 'file': str(folder / name), 'alerts': [], 'history': [],
            'sha256': 'ab' * 32, 'processed_at': '2026-10-01T12:00:00+00:00', **extra}
    (folder / 'relatorios').mkdir(exist_ok=True)
    (folder / 'relatorios' / (Path(name).stem + '.json')).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


class OversizedReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)

    def test_oversized_report_is_refused_without_being_read(self):
        """Antes: um relatório de 600 MB levava 10 s e 1,2 GB de memória a cada atualização da tabela."""
        write_report(self.root, 'normal.pdf')
        big = self.root / 'relatorios' / 'enorme.json'
        with big.open('wb') as stream:                       # arquivo esparso: não ocupa disco de verdade
            stream.write(b'{"status": "aprovados"'); stream.seek(MAX_REPORT_BYTES + 1); stream.write(b'}')
        real = Path.read_text
        def guarded(path, *a, **k):
            if path.name == 'enorme.json': raise AssertionError('não deveria ler o relatório gigante')
            return real(path, *a, **k)
        start = time.monotonic()
        with patch.object(Path, 'read_text', guarded): rows, errors = ReviewStore(self.root).list_reports()
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual([r[1]['original_name'] for r in rows], ['normal.pdf'])
        self.assertEqual([e[0] for e in errors], ['enorme.json']); self.assertIn('grande demais', errors[0][1])

    def test_a_large_but_legitimate_report_still_loads(self):
        write_report(self.root, 'longo.pdf', text='palavra ' * 500_000)   # ~4 MB de texto, bem acima do normal
        rows, errors = ReviewStore(self.root).list_reports()
        self.assertEqual((len(rows), errors), (1, []))


class CsvExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        write_report(self.root, 'Currículo_João.pdf', alerts=[{'type': 'baixo_contraste'}, {'type': 'instrucao_ia'}])
        write_report(self.root, '=cmd.pdf'); self.store = ReviewStore(self.root); self.target = self.root / 'inventario.csv'

    def test_default_export_is_unchanged_comma_without_bom(self):
        self.store.export_csv(self.target)
        raw = self.target.read_bytes()
        self.assertTrue(raw.startswith(b'arquivo,status,alertas,sha256,processado_em,revisoes'))
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))

    def test_excel_export_uses_semicolon_and_utf8_bom(self):
        """Excel em português separa por ';' e só reconhece UTF-8 com BOM; sem isso tudo cai na coluna A e os acentos quebram."""
        self.store.export_csv(self.target, excel_br=True)
        raw = self.target.read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertTrue(raw.decode('utf-8-sig').startswith('arquivo;status;alertas;sha256;processado_em;revisoes'))
        with self.target.open(encoding='utf-8-sig', newline='') as stream: rows = list(csv.reader(stream, delimiter=';'))
        self.assertEqual({len(r) for r in rows}, {6})                                        # sempre 6 colunas, nenhuma célula "vazou"
        by_name = {r[0]: r for r in rows[1:]}
        self.assertIn('Currículo_João.pdf', by_name)                                         # acentos intactos
        self.assertEqual(by_name['Currículo_João.pdf'][2], 'baixo_contraste; instrucao_ia')  # o ';' dentro da célula não quebra a coluna

    def test_formula_neutralization_still_applies_in_excel_mode(self):
        self.store.export_csv(self.target, excel_br=True)
        with self.target.open(encoding='utf-8-sig', newline='') as stream: names = [r[0] for r in csv.reader(stream, delimiter=';')][1:]
        self.assertIn("'=cmd.pdf", names); self.assertNotIn('=cmd.pdf', names)


if __name__ == '__main__': unittest.main()
