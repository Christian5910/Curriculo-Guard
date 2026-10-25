"""Script de construção do executável para Windows (EXE/construcao/construir.py).

O build real baixa ~120 MB e é verificado à parte (EXE/construcao/verificar_portatil.py, job "portatil-windows" da CI);
aqui ficam as peças que não dependem de internet: o leitor de DLLs, a checagem de dependências e a coerência de versões.
"""
import importlib.util
import re
import shutil
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONSTRUCAO = RAIZ / 'EXE' / 'construcao'
LANCADOR = CONSTRUCAO / 'lancador' / 'CurriculoGuard.exe'

spec = importlib.util.spec_from_file_location('construir', CONSTRUCAO / 'construir.py')
construir = importlib.util.module_from_spec(spec); spec.loader.exec_module(construir)


class PeReaderTests(unittest.TestCase):
    def test_launcher_imports_only_windows_system_dlls(self):
        """O lançador compilado só pode depender de DLLs que existem em qualquer Windows (lido do próprio .exe)."""
        self.assertEqual(construir.dlls_importadas(LANCADOR), {'kernel32.dll', 'user32.dll', 'shell32.dll', 'msvcrt.dll'})

    def test_files_that_are_not_pe_have_no_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            for nome, conteudo in (('texto.dll', b'isto nao e um executavel de Windows'), ('curto.dll', b'MZ'), ('cabecalho.dll', LANCADOR.read_bytes()[:64])):
                (Path(tmp) / nome).write_bytes(conteudo); self.assertEqual(construir.dlls_importadas(Path(tmp) / nome), set(), nome)

    def test_a_truncated_pe_fails_loudly_instead_of_passing_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            cortado = Path(tmp) / 'cortado.dll'; cortado.write_bytes(LANCADOR.read_bytes()[:1200])   # cabeçalhos válidos, dados cortados
            with self.assertRaisesRegex(ValueError, 'corrompido ou cortado'): construir.dlls_importadas(cortado)


class MissingDependencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.pasta = Path(self.tmp.name)
        shutil.copy2(LANCADOR, self.pasta / 'programa.exe')

    def test_windows_system_dlls_are_not_reported(self):
        self.assertEqual(construir.dependencias_ausentes(self.pasta), {})

    def test_a_dll_that_is_neither_windows_nor_shipped_is_reported(self):
        """Foi assim que a msvcp140.dll do PyMuPDF passou despercebida: o Wine a fornece, o Windows limpo não."""
        original = construir.SISTEMA
        try:
            construir.SISTEMA = re.compile(r'^kernel32\.dll$|^msvcrt\.dll$|^user32\.dll$', re.I)   # finge que shell32 não é do sistema
            self.assertEqual(set(construir.dependencias_ausentes(self.pasta)), {'shell32.dll'})
            shutil.copy2(LANCADOR, self.pasta / 'shell32.dll')                                     # agora uma DLL com esse nome vai no pacote
            self.assertEqual(construir.dependencias_ausentes(self.pasta), {})
        finally:
            construir.SISTEMA = original

    def test_visual_cpp_runtime_is_completed_from_a_bundled_copy(self):
        runtime = self.pasta / 'runtime'; (runtime / 'Lib' / 'site-packages' / 'numpy.libs').mkdir(parents=True)
        copia = runtime / 'Lib' / 'site-packages' / 'numpy.libs' / 'msvcp140-abc123.dll'; copia.write_bytes(b'conteudo-da-dll')
        construir.completar_visual_cpp(runtime)
        self.assertEqual((runtime / 'msvcp140.dll').read_bytes(), b'conteudo-da-dll')
        (runtime / 'msvcp140.dll').write_bytes(b'ja existia'); construir.completar_visual_cpp(runtime)
        self.assertEqual((runtime / 'msvcp140.dll').read_bytes(), b'ja existia')                   # não sobrescreve uma DLL já presente
        vazio = self.pasta / 'outro'; vazio.mkdir(); construir.completar_visual_cpp(vazio)         # sem cópia disponível: não quebra
        self.assertFalse((vazio / 'msvcp140.dll').exists())


class ReleaseConsistencyTests(unittest.TestCase):
    def test_every_place_that_shows_the_version_agrees(self):
        """APP_VERSION (relatórios), o .exe (propriedades do arquivo) e o instalador precisam mostrar a mesma versão."""
        versao = re.search(r"APP_VERSION = '([\d.]+)'", (RAIZ / 'curriculo_guard' / 'engine.py').read_text(encoding='utf-8')).group(1)
        rc = (CONSTRUCAO / 'lancador' / 'lancador.rc').read_text(encoding='utf-8')
        nsi = (CONSTRUCAO / 'instalador' / 'instalador.nsi').read_text(encoding='utf-8')
        self.assertIn(f'FILEVERSION {versao.replace(".", ",")},0,0', rc)
        self.assertIn(f'VALUE "FileVersion", "{versao}"', rc)
        self.assertIn(f'!define VERSAO "{versao}"', nsi)
        self.assertEqual((RAIZ / 'CHANGELOG.md').read_text(encoding='utf-8').splitlines()[0], f'# Versão {versao}')   # o topo do CHANGELOG é esta versão

    def test_the_build_script_copies_files_that_exist_in_the_project(self):
        for relativo in ('app.py', 'curriculo_guard/engine.py', 'curriculo_guard/workflow.py', 'curriculo_guard/review_ui.py', 'assets/icon.ico', 'requirements.txt'):
            self.assertTrue((RAIZ / relativo).is_file(), relativo)
        self.assertTrue((CONSTRUCAO / 'LEIA-ME-portatil.txt').is_file()); self.assertTrue(LANCADOR.is_file())


if __name__ == '__main__': unittest.main()
