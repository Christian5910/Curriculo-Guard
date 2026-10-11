"""Detector de frases da v2.0 (4 padrões), preservado só como linha de base.

Permite reproduzir a comparação "antes e depois" sem manter o código antigo no motor.
"""
import re, unicodedata

PATTERNS = [
    ('instrucao_ia', r'(?i)(ignore (all )?(previous|prior) instructions|ignore todas as instru[cç][oõ]es|desconsidere (as )?instru[cç][oõ]es anteriores)'),
    ('papel_sistema', r'(?i)(\[\s*(system|developer|assistant)\s*\]|<\s*/?\s*(system|developer|assistant)\s*>|\b(system prompt|developer message)\b)'),
    ('comando_avaliacao', r'(?i)(approve (this|the) (candidate|resume)|aprove (este|o) candidato|atribua (nota|pontua[cç][aã]o) m[aá]xima|give (me|this candidate) (a )?(perfect|maximum) score)'),
    ('exfiltracao', r'(?i)(send|envie|transmita).{0,70}(dados|data|curr[ií]culos|resumes).{0,100}(https?://|email|e-mail|@)'),
]

def normalized(text):
    text = unicodedata.normalize('NFKC', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return re.sub(r'\s+', ' ', text)

def detects(text):
    text = normalized(text)
    return any(re.search(pattern, text) for _, pattern in PATTERNS)
