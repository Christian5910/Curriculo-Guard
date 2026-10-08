"""Persistência, revisão humana e exportação: nenhuma decisão de contratação.

Todas as gravações de JSON são atômicas. O histórico pertence ao documento;
conteúdo extraído e comentários do revisor continuam sendo dados não confiáveis.
"""
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


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

    def list_reports(self, status='todos', query=''):
        """Lista apenas JSONs válidos; relatórios corrompidos são contabilizados."""
        rows, errors = [], []
        for path in sorted(self.reports.glob('*.json'), reverse=True):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data, dict): raise ValueError('Relatório não é objeto JSON')
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
        """
        report_path = Path(report_path).resolve()
        if report_path.parent != self.reports.resolve(): raise ValueError('Relatório fora da saída.')
        if status not in ('aprovados','rejeitados','verificacao_humana'): raise ValueError('Destino inválido.')
        if not reviewer.strip() or not reason.strip(): raise ValueError('Informe revisor e justificativa.')
        data = json.loads(report_path.read_text(encoding='utf-8'))
        source = self.checked_pdf(data)
        if data.get('status') in ('quarentena','duplicados'):
            raise ValueError('Reprocesse este arquivo antes de tomar uma decisão.')
        if status == 'aprovados' and (data.get('error') or not data.get('text','').strip()):
            raise ValueError('Não há texto filtrado válido para liberar. Reprocesse ou revise fora do app.')
        old_status = data['status']
        target = self.root / status / source.name
        if not target.resolve().is_relative_to(self.root): raise ValueError('Destino aponta para fora da saída.')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Revogar primeiro evita TXT disponível enquanto o documento é bloqueado.
        text_path = report_path.with_suffix('.txt')
        text_path.unlink(missing_ok=True)
        if target != source:
            import shutil
            if target.exists(): raise ValueError('Já existe documento com esse nome no destino.')
            shutil.copy2(source, target)
        data.update(file=str(target), status=status)
        data.setdefault('history', []).append({'time':datetime.now(timezone.utc).isoformat(),
            'from':old_status,'to':status,'reviewer':reviewer.strip(),'reason':reason.strip()})
        try: write_report(report_path, data)
        except Exception:
            if target != source: target.unlink(missing_ok=True)
            raise
        if target != source: source.unlink()
        if status == 'aprovados': atomic_write(text_path, data['text'])
        return data

    def export_csv(self, path):
        """Exporta inventário sem texto do currículo e neutraliza fórmulas CSV."""
        def cell(value):
            value = str(value)
            if value.lstrip().startswith(('=', '+', '-', '@')): return "'" + value
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
