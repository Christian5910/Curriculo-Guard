"""Constrói o Currículo Guard portátil para Windows (e, se possível, o instalador).

Roda em Windows, Linux ou macOS, só precisa de Python 3.9+ e internet (a primeira vez). Uso, na raiz do projeto:

    python EXE/construcao/construir.py              # pasta portátil + instalador (se o NSIS existir)
    python EXE/construcao/construir.py --zip        # também cria CurriculoGuard-Portatil.zip
    python EXE/construcao/construir.py --sem-instalador
    python EXE/construcao/construir.py --atualizar  # baixa tudo de novo, ignorando o cache

O que ele faz:
  1. baixa o Python 3.12 para Windows (versão "standalone", que já traz o Tk da interface) e confere o SHA-256;
  2. baixa as versões para Windows das bibliotecas de requirements.txt (+ pypdfium2) com o pip, sem instalá-las aqui;
  3. monta EXE/CurriculoGuard-Portatil/:  runtime/ (Python + bibliotecas)  app/ (o programa)  CurriculoGuard.exe;
  4. confere os arquivos essenciais e se alguma DLL exigida ficou de fora (o que quebraria num Windows limpo);
  5. gera EXE/CurriculoGuard-Setup.exe com o NSIS (makensis), se estiver instalado.

Nada disso depende do Windows: o Python e as bibliotecas são copiados, não executados. Explicação passo a passo
para quem nunca criou um executável: EXE/LEIA-ME.md.
"""
import argparse
import hashlib
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent        # EXE/construcao
EXE = AQUI.parent                              # EXE
RAIZ = EXE.parent                              # raiz do projeto
CACHE = AQUI / 'cache'
PORTATIL = EXE / 'CurriculoGuard-Portatil'
LANCADOR = AQUI / 'lancador' / 'CurriculoGuard.exe'
INSTALADOR_NSI = AQUI / 'instalador' / 'instalador.nsi'

# Python standalone (python-build-standalone): versão e SHA-256 fixos, para o resultado ser reproduzível e para
# o download não poder ser trocado sem o script perceber.
PYTHON_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/20260414/'
              'cpython-3.12.13%2B20260414-x86_64-pc-windows-msvc-install_only_stripped.tar.gz')
PYTHON_SHA256 = 'd785d2e901a8194dcdb8c23c2b37a46ed84fdc04e87398dc5b832644330de71e'
EXTRAS = ['pypdfium2>=5,<6']   # opcional no programa: segunda opinião de renderizador

# O que sai do pacote final para ele ficar menor (nada disso é usado pelo programa).
REMOVER_RUNTIME = ['Lib/test', 'Lib/idlelib', 'Lib/turtledemo', 'Lib/ensurepip', 'Lib/lib2to3', 'Lib/site-packages/pip',
                   'Lib/site-packages/setuptools', 'Lib/site-packages/_distutils_hack', 'Scripts', 'include', 'libs']
ESSENCIAIS = ['CurriculoGuard.exe', 'runtime/python.exe', 'runtime/pythonw.exe', 'runtime/python312.dll', 'runtime/msvcp140.dll', 'runtime/vcruntime140.dll', 'runtime/vcruntime140_1.dll', 'runtime/DLLs/_tkinter.pyd',
              'runtime/DLLs/tcl86t.dll', 'runtime/tcl/tcl8.6/init.tcl', 'runtime/tcl/tk8.6/tk.tcl',
              'runtime/Lib/site-packages/pymupdf/__init__.py', 'runtime/Lib/site-packages/numpy/__init__.py',
              'runtime/Lib/site-packages/requests/__init__.py', 'runtime/Lib/site-packages/pypdfium2/__init__.py',
              'app/app.py', 'app/curriculo_guard/engine.py', 'app/curriculo_guard/workflow.py', 'app/curriculo_guard/review_ui.py',
              'app/assets/icon_256.png']


# DLLs que já existem em qualquer Windows 10/11 (pasta System32): não precisam ir no pacote.
SISTEMA = re.compile(r'^(api-ms-win-.*|ext-ms-win-.*|kernel32|kernelbase|ntdll|user32|gdi32|gdi32full|advapi32|shell32|shlwapi|ole32|oleaut32|'
                     r'ws2_32|wsock32|crypt32|bcrypt|bcryptprimitives|rpcrt4|msvcrt|ucrtbase|version|winmm|imm32|netapi32|userenv|secur32|iphlpapi|'
                     r'mswsock|psapi|setupapi|comdlg32|comctl32|combase|sechost|cfgmgr32|wintrust|dnsapi|normaliz|shcore|uxtheme|dwmapi|msimg32|'
                     r'oledlg|ncrypt|cryptsp|rstrtmgr|nsi|win32u|powrprof|wldap32|opengl32|glu32|hid|wtsapi32|mpr|propsys|windowscodecs|urlmon|'
                     r'wininet|shfolder|authz|credui|dbghelp|virtdisk|ktmw32|pdh|dbgcore|cabinet|msi)\.(dll|drv)$', re.I)


def passo(texto):
    print(f'\n== {texto}')


def sha256(caminho):
    resumo = hashlib.sha256()
    with open(caminho, 'rb') as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b''):
            resumo.update(bloco)
    return resumo.hexdigest()


def dlls_importadas(caminho):
    """Nomes (minúsculos) das DLLs que um .exe/.dll/.pyd de Windows importa. Leitor de PE em Python puro.

    Arquivo que não é um executável de Windows (ou é pequeno demais para ser) devolve conjunto vazio. Um PE de
    verdade cortado ou corrompido levanta ValueError: um binário quebrado não pode passar em silêncio para o pacote.
    """
    dados = Path(caminho).read_bytes()
    if len(dados) < 64 or dados[:2] != b'MZ': return set()
    try:
        pe = struct.unpack_from('<I', dados, 0x3C)[0]
        if dados[pe:pe + 4] != b'PE\0\0': return set()
        secoes_n, = struct.unpack_from('<H', dados, pe + 6); tamanho_opcional, = struct.unpack_from('<H', dados, pe + 20)
        opcional = pe + 24; magico, = struct.unpack_from('<H', dados, opcional)
        diretorios = opcional + (112 if magico == 0x20b else 96)
        importacao, = struct.unpack_from('<I', dados, diretorios + 8)   # entrada 1 dos diretórios de dados: tabela de importação
        if not importacao: return set()
        secoes = []
        for i in range(secoes_n):
            _, tam_virtual, virtual, tam_bruto, bruto = struct.unpack_from('<8sIIII', dados, opcional + tamanho_opcional + 40 * i)
            secoes.append((virtual, max(tam_virtual, tam_bruto), bruto))

        def posicao(rva):
            for virtual, tamanho, bruto in secoes:
                if virtual <= rva < virtual + tamanho: return rva - virtual + bruto
            return None
        nomes, atual = set(), posicao(importacao)
        while atual is not None:
            nome_rva = struct.unpack_from('<I', dados, atual + 12)[0]
            if nome_rva == 0: break
            inicio = posicao(nome_rva)
            nomes.add(dados[inicio:dados.index(b'\0', inicio)].decode('ascii', 'replace').lower())
            atual += 20
        return nomes
    except (struct.error, ValueError, TypeError) as erro:
        raise ValueError(f'{caminho}: executável de Windows corrompido ou cortado ({erro})') from erro


def dependencias_ausentes(pasta):
    """{dll: [arquivos que a exigem]} para toda DLL que NÃO é do Windows e NÃO está dentro do pacote.

    No Windows de um usuário sem o "Visual C++ Redistributable", uma DLL dessas ausente faz o programa falhar com
    "msvcp140.dll não encontrada". O Wine e a máquina de quem desenvolve escondem esse erro, por isso é conferido aqui.
    """
    pasta = Path(pasta)
    binarios = [f for f in pasta.rglob('*') if f.suffix.lower() in ('.exe', '.dll', '.pyd')]
    incluidas = {f.name.lower() for f in binarios}
    ausentes = {}
    for binario in binarios:
        for dll in dlls_importadas(binario):
            if dll not in incluidas and not SISTEMA.match(dll): ausentes.setdefault(dll, []).append(str(binario.relative_to(pasta)))
    return ausentes


def completar_visual_cpp(runtime):
    """Alguns pacotes (PyMuPDF) usam msvcp140.dll sem trazê-la; o NumPy traz uma cópia renomeada. Copia para ao lado do Python.

    A Microsoft permite distribuir as DLLs do Visual C++ junto do programa ("implantação local ao aplicativo").
    """
    destino = runtime / 'msvcp140.dll'
    if destino.exists(): return
    copias = sorted((runtime / 'Lib' / 'site-packages').glob('*.libs/msvcp140*.dll'))
    if copias:
        shutil.copy2(copias[0], destino)
        print(f'msvcp140.dll completada a partir de {copias[0].name}')


def baixar_python(atualizar):
    destino = CACHE / 'python-windows.tar.gz'
    if atualizar and destino.exists(): destino.unlink()
    if not destino.exists():
        print('baixando o Python para Windows (~22 MB)...')
        CACHE.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(PYTHON_URL, destino)
    if sha256(destino) != PYTHON_SHA256:
        destino.unlink()
        raise SystemExit('O Python baixado não confere com o SHA-256 esperado. O arquivo foi apagado; tente de novo.')
    print('Python conferido (SHA-256 ok).')
    return destino


def baixar_bibliotecas(atualizar):
    pasta = CACHE / 'wheels'
    if atualizar and pasta.exists(): shutil.rmtree(pasta)
    if not list(pasta.glob('*.whl')):
        print('baixando as bibliotecas para Windows...')
        pasta.mkdir(parents=True, exist_ok=True)
        comando = [sys.executable, '-m', 'pip', 'download', '-q', '--dest', str(pasta), '--platform', 'win_amd64', '--python-version', '3.12',
                   '--implementation', 'cp', '--abi', 'cp312', '--only-binary=:all:', '-r', str(RAIZ / 'requirements.txt'), *EXTRAS]
        subprocess.run(comando, check=True)
    rodas = sorted(pasta.glob('*.whl'))
    print(f'{len(rodas)} bibliotecas prontas.')
    return rodas


def extrair_python(arquivo, destino):
    with tempfile.TemporaryDirectory() as temporaria:
        with tarfile.open(arquivo) as tar:
            tar.extractall(temporaria, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
        shutil.move(str(Path(temporaria) / 'python'), str(destino))


def aparar(runtime):
    """Remove o que o programa não usa (testes, instalador de pacotes, bytecode, símbolos de depuração)."""
    antes = sum(f.stat().st_size for f in runtime.rglob('*') if f.is_file())
    for relativo in REMOVER_RUNTIME:
        alvo = runtime / relativo
        if alvo.is_dir(): shutil.rmtree(alvo)
    for padrao in ('__pycache__', 'tests', 'test'):
        for pasta in list((runtime / 'Lib' / 'site-packages').rglob(padrao)):
            if pasta.is_dir() and pasta.parent.name not in ('testing',): shutil.rmtree(pasta, ignore_errors=True)
    for pasta in list(runtime.rglob('__pycache__')): shutil.rmtree(pasta, ignore_errors=True)
    for arquivo in list(runtime.rglob('*.pdb')) + list((runtime / 'DLLs').glob('_test*.pyd')): arquivo.unlink()
    depois = sum(f.stat().st_size for f in runtime.rglob('*') if f.is_file())
    print(f'runtime aparado: {antes / 2**20:.0f} MB -> {depois / 2**20:.0f} MB')


def copiar_programa(destino):
    destino.mkdir(parents=True)
    shutil.copy2(RAIZ / 'app.py', destino / 'app.py')
    shutil.copytree(RAIZ / 'curriculo_guard', destino / 'curriculo_guard', ignore=shutil.ignore_patterns('__pycache__'))
    assets = destino / 'assets'; assets.mkdir()
    for arquivo in (RAIZ / 'assets').glob('icon*'): shutil.copy2(arquivo, assets / arquivo.name)


def montar(arquivo_python, rodas):
    if PORTATIL.exists(): shutil.rmtree(PORTATIL)
    PORTATIL.mkdir(parents=True)
    runtime = PORTATIL / 'runtime'
    extrair_python(arquivo_python, runtime)
    site = runtime / 'Lib' / 'site-packages'; site.mkdir(parents=True, exist_ok=True)
    for roda in rodas:   # uma "wheel" é um zip: descompactar na pasta de bibliotecas equivale a instalar
        with zipfile.ZipFile(roda) as zip_roda: zip_roda.extractall(site)
    completar_visual_cpp(runtime)
    aparar(runtime)
    copiar_programa(PORTATIL / 'app')
    if not LANCADOR.exists():
        raise SystemExit(f'Falta o lançador compilado: {LANCADOR}\nCompile com EXE/construcao/lancador/compilar_lancador.sh (Linux) ou use o que veio no projeto.')
    shutil.copy2(LANCADOR, PORTATIL / 'CurriculoGuard.exe')
    shutil.copy2(AQUI / 'LEIA-ME-portatil.txt', PORTATIL / 'LEIA-ME.txt')
    versoes = '\n'.join(f'{roda.name}  sha256={sha256(roda)}' for roda in rodas)
    (AQUI / 'versoes_empacotadas.txt').write_text(f'python-windows.tar.gz  sha256={PYTHON_SHA256}\n{versoes}\n', encoding='utf-8')


def conferir():
    faltando = [item for item in ESSENCIAIS if not (PORTATIL / item).exists()]
    if faltando: raise SystemExit('Arquivos essenciais ausentes:\n  ' + '\n  '.join(faltando))
    ausentes = dependencias_ausentes(PORTATIL)
    if ausentes:
        raise SystemExit('DLLs exigidas e ausentes do pacote (o programa falharia num Windows sem o Visual C++):\n  ' +
                         '\n  '.join(f'{dll}  <- {arquivos[0]} (+{len(arquivos) - 1})' for dll, arquivos in sorted(ausentes.items())))
    tamanho = sum(f.stat().st_size for f in PORTATIL.rglob('*') if f.is_file())
    print(f'pasta portátil pronta: {PORTATIL} ({tamanho / 2**20:.0f} MB, {len(ESSENCIAIS)} arquivos essenciais conferidos)')


def gerar_instalador():
    makensis = shutil.which('makensis') or shutil.which('makensis.exe')
    if not makensis:
        for candidato in (r'C:\Program Files (x86)\NSIS\makensis.exe', r'C:\Program Files\NSIS\makensis.exe'):
            if Path(candidato).exists(): makensis = candidato
    if not makensis:
        print('NSIS (makensis) não encontrado: o instalador não foi gerado. A pasta portátil continua válida.\n'
              'Para gerar o instalador, instale o NSIS (https://nsis.sourceforge.io) e rode este script de novo.')
        return False
    subprocess.run([makensis, '-V2', str(INSTALADOR_NSI)], check=True, cwd=INSTALADOR_NSI.parent)
    instalador = EXE / 'CurriculoGuard-Setup.exe'
    print(f'instalador pronto: {instalador} ({instalador.stat().st_size / 2**20:.0f} MB)')
    return True


def compactar():
    destino = EXE / 'CurriculoGuard-Portatil.zip'
    if destino.exists(): destino.unlink()
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_saida:
        for arquivo in sorted(PORTATIL.rglob('*')):
            if arquivo.is_file(): zip_saida.write(arquivo, Path('CurriculoGuard-Portatil') / arquivo.relative_to(PORTATIL))
    print(f'zip pronto: {destino} ({destino.stat().st_size / 2**20:.0f} MB)')


def main():
    analisador = argparse.ArgumentParser(description='Constrói o Currículo Guard portátil e o instalador para Windows.')
    analisador.add_argument('--zip', action='store_true', help='também cria CurriculoGuard-Portatil.zip')
    analisador.add_argument('--sem-instalador', action='store_true', help='não gera o CurriculoGuard-Setup.exe')
    analisador.add_argument('--atualizar', action='store_true', help='baixa o Python e as bibliotecas de novo')
    opcoes = analisador.parse_args()
    passo('1/5  Python para Windows'); arquivo_python = baixar_python(opcoes.atualizar)
    passo('2/5  Bibliotecas para Windows'); rodas = baixar_bibliotecas(opcoes.atualizar)
    passo('3/5  Montando a pasta portátil'); montar(arquivo_python, rodas)
    passo('4/5  Conferindo'); conferir()
    passo('5/5  Instalador')
    if opcoes.sem_instalador: print('pulado (--sem-instalador).')
    else: gerar_instalador()
    if opcoes.zip: passo('Compactando'); compactar()
    print('\nPronto.')


if __name__ == '__main__':
    main()
