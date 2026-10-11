"""Mede recall e falsos positivos da detecção de frases, no motor atual e na linha de base v2.0.

Uso (na raiz do projeto):
    python -m evaluation.run_phrases            # mostra a tabela e as frases não detectadas
    python -m evaluation.run_phrases --check    # sai com erro se algum limite for violado (usado na CI)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import instruction_alerts
from evaluation import baseline_v2_0 as baseline
from evaluation import corpus

# Limites que a CI exige. O recall inédito mínimo é o resultado medido na versão 2.2.
MIN_HOLDOUT_RECALL = 22 / 30


def evaluate(detect, positives, negatives):
    missed = [s for s in positives if not detect(s)]
    false_alarms = [s for s in negatives if detect(s)]
    return len(positives) - len(missed), missed, false_alarms


def main(check=False):
    current = lambda text: bool(instruction_alerts(text))
    sets = (('Desenvolvimento (ajustado)', corpus.DEVELOPMENT_POSITIVES, corpus.DEVELOPMENT_NEGATIVES),
            ('Inédito (holdout)', corpus.HOLDOUT_POSITIVES, corpus.HOLDOUT_NEGATIVES))
    problems, results = [], {}
    print(f"{'conjunto':28s} {'detector':12s} {'recall':>10s} {'falsos positivos':>18s}")
    for label, positives, negatives in sets:
        for name, detect in (('v2.0', baseline.detects), ('atual', current)):
            hit, missed, false_alarms = evaluate(detect, positives, negatives)
            results[(label, name)] = (hit, len(positives), missed, false_alarms)
            print(f"{label:28s} {name:12s} {hit:>4d}/{len(positives):<5d} {len(false_alarms):>10d}/{len(negatives)}")
    hit, total, missed, false_alarms = results[('Inédito (holdout)', 'atual')]
    if missed:
        print('\nNão detectadas no conjunto inédito (limite conhecido):')
        for text in missed: print('  -', text)
    if false_alarms:
        print('\nFalsos positivos no conjunto inédito:')
        for text in false_alarms: print('  -', text)
    dev_hit, dev_total, _, dev_false = results[('Desenvolvimento (ajustado)', 'atual')]
    if dev_hit != dev_total: problems.append(f'regressão no conjunto de desenvolvimento: {dev_hit}/{dev_total}')
    if dev_false: problems.append(f'falsos positivos no desenvolvimento: {len(dev_false)}')
    if false_alarms: problems.append(f'falsos positivos no conjunto inédito: {len(false_alarms)}')
    if hit / total < MIN_HOLDOUT_RECALL - 1e-9: problems.append(f'recall inédito abaixo do mínimo: {hit}/{total}')
    if check and problems:
        print('\nFALHOU:', '; '.join(problems)); return 1
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main(check='--check' in sys.argv))
