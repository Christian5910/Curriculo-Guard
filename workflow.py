"""Persistência, revisão humana e exportação: nenhuma decisão de contratação.

Todas as gravações de JSON são atômicas. O histórico pertence ao documento;
conteúdo extraído e comentários do revisor continuam sendo dados não confiáveis.
"""
import csv
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


CHILD_MEMORY_MB = 2048   # teto de memória virtual dos processos filhos que leem PDFs não confiáveis (POSIX); PDFs normais usam < 450 MB


def limit_memory(megabytes):
    """Teto de memória virtual do processo atual (POSIX). No Windows não há equivalente simples; vale só o prazo.

    Vive aqui, e não em engine.py, para a prévia da revisão aplicá-lo sem importar numpy no processo filho.
    """
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (megabytes * 2**20, megabytes * 2**20))
    except (ImportError, ValueError, OSError): pass


def sha256_file(path):
    """Calcula hash em blocos, evitando carregar PDFs grandes na memória."""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path, text):
    """Publica um arquivo completo com replace; limpa temporários em falhas."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def write_report(path, data):
    """JSON legível, sem permitir valores NaN não padronizados."""
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))


class ReviewStore:
    """Gerencia relatórios existentes e decisões documentais auditáveis."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.reports = self.root / 'relatorios'
        if not self.reports.resolve().is_relative_to(self.root):
            raise ValueError('Pasta de relatórios aponta para fora da saída.')

    @staticmethod
    def load_report(path):
        """Lê um relatório e valida a estrutura que a interface consome.

        Relatórios são dados não confiáveis: JSON profundamente aninhado ou com
        campos de tipo errado viram erro contabilizado, nunca exceção na tela.
        """
        try: data = json.loads(Path(path).read_text(encoding='utf-8'))
        except RecursionError as exc: raise ValueError('JSON aninhado em excesso') from exc
        if not isinstance(data, dict): raise ValueError('Relatório não é objeto JSON')
        alerts, history = data.get('alerts', []), data.get('history', [])
        if not isinstance(alerts, list) or not all(isinstance(a, dict) for a in alerts):
            raise ValueError('Campo alerts inválido')
        if not isinstance(history, list) or not all(isinstance(h, dict) and all(isinstance(h.get(k), str) for k in ('time','reviewer','to','reason')) for h in history):
            raise ValueError('Campo history inválido')
        if not isinstance(data.get('text', ''), str): raise ValueError('Campo text inválido')
        return data

    def list_reports(self, status='todos', query=''):
        """Lista apenas JSONs válidos; relatórios corrompidos são contabilizados."""
        rows, errors = [], []
        for path in sorted(self.reports.glob('*.json'), reverse=True):
            try:
                data = self.load_report(path)
                if status != 'todos' and data.get('status') != status: continue
                name = data.get('original_name', Path(data.get('file','')).name)
                if query.casefold() not in str(name).casefold(): continue
                rows.append((path, data))
            except (OSError, ValueError, TypeError) as exc: errors.append((path.name, str(exc)))
        return rows, errors

    def checked_pdf(self, report):
        """Rejeita caminho fora da saída, symlinks de fuga e arquivo alterado."""
        path = Path(report['file']).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError('Arquivo fora da saída ou indisponível.')
        if not report.get('sha256') or sha256_file(path) != report['sha256']:
            raise ValueError('Integridade falhou: PDF mudou desde a análise.')
        return path

    def decide(self, report_path, status, reviewer, reason):
        """Reclassifica com cópia verificada; mantém eventos no mesmo relatório.

        Aprovação libera somente o texto filtrado já existente. Não restaura
        texto invisível nem transforma aprovação documental em contratação.

        Todas as validações ocorrem ANTES de revogar o TXT liberado. A revogação vem primeiro para que o
        texto nunca fique disponível enquanto o documento é bloqueado, mas, se a decisão falhar depois
        (disco cheio, arquivo em uso, relatório não gravado), o TXT anterior é restaurado: um relatório
        "aprovados" nunca fica sem o texto que o acompanha.
        """
        report_path = Path(report_path).resolve()
        if report_path.parent != self.reports.resolve(): raise ValueError('Relatório fora da saída.')
        if status not in ('aprovados','rejeitados','verificacao_humana'): raise ValueError('Destino inválido.')
        if not reviewer.strip() or not reason.strip(): raise ValueError('Informe revisor e justificativa.')
        data = self.load_report(report_path)
        if not isinstance(data.get('file'), str) or not isinstance(data.get('status'), str): raise ValueError('Relatório sem arquivo ou destino válido.')
        source = self.checked_pdf(data)
        if data.get('status') in ('quarentena','duplicados'):
            raise ValueError('Reprocesse este arquivo antes de tomar uma decisão.')
        if status == 'aprovados' and (data.get('error') or not data.get('text','').strip()):
            raise ValueError('Não há texto filtrado válido para liberar. Reprocesse ou revise fora do app.')
        old_status = data['status']
        target = self.root / status / source.name
        if not target.resolve().is_relative_to(self.root): raise ValueError('Destino aponta para fora da saída.')
        if target != source and target.exists(): raise ValueError('Já existe documento com esse nome no destino.')
        target.parent.mkdir(parents=True, exist_ok=True)
        text_path = report_path.with_suffix('.txt')
        previous_text = text_path.read_bytes() if text_path.is_file() else None
        text_path.unlink(missing_ok=True)   # revogar primeiro: sem TXT disponível enquanto o documento é bloqueado
        try:
            if target != source:
                shutil.copy2(source, target)
                if sha256_file(target) != data['sha256']: raise ValueError('Integridade falhou: PDF mudou durante a cópia.')
            data.update(file=str(target), status=status)
            data.setdefault('history', []).append({'time':datetime.now(timezone.utc).isoformat(),
                'from':old_status,'to':status,'reviewer':reviewer.strip(),'reason':reason.strip()})
            write_report(report_path, data)
        except Exception:
            if target != source: target.unlink(missing_ok=True)
            if previous_text is not None: atomic_write(text_path, previous_text.decode('utf-8'))   # decisão não aplicada: o TXT volta
            raise
        # O relatório já aponta para o destino: daqui em diante nada mais pode desfazer a decisão.
        if status == 'aprovados': atomic_write(text_path, data['text'])
        if target != source:
            try: source.unlink()
            except OSError: pass   # cópia antiga em uso (ex.: Windows); o relatório já aponta para o novo arquivo
        return data

    def export_csv(self, path):
        """Exporta inventário sem texto do currículo e neutraliza fórmulas CSV."""
        def cell(value):
            value = str(value)
            if value.lstrip().startswith(('=', '+', '-', '@')) or value[:1] in ('\t', '\r'): return "'" + value
            return value
        import io
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['arquivo','status','alertas','sha256','processado_em','revisoes'])
        rows, errors = self.list_reports()
        for _, data in rows:
            writer.writerow([cell(data.get('original_name','')), cell(data.get('status','')),
                cell('; '.join(a.get('type','') for a in data.get('alerts',[]))),
                cell(data.get('sha256','')), cell(data.get('processed_at','')),len(data.get('history',[]))])
        atomic_write(path, stream.getvalue())
        return len(rows), len(errors)
