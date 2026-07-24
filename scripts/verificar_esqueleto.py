#!/usr/bin/env python3
"""Falha se a cópia vendorizada do esqueleto neste repositório foi editada
direto, em vez de editada em _esqueleto/ e redistribuída por sync.py.

O esqueleto (base.css, base.js, sgx_base.py, DESIGN.md) tem uma única fonte
canônica, em _esqueleto/, fora dos 4 repositórios. Nada impede alguém — ou o
Claude numa sessão futura — de abrir SGCD/base.js e corrigir ali: funciona,
passa no lint, e o próximo `python _esqueleto/sync.py` apaga a correção sem
avisar. Este script é o alarme: o CI de cada sistema o roda e quebra o build
quando a cópia local divergiu do que o sync gravou.

O hash normaliza CRLF -> LF de propósito: o repositório guarda LF e o runner
Windows faz checkout com CRLF, então comparar bytes crus daria falso positivo.

Uso:  python scripts/verificar_esqueleto.py

Este arquivo e o _esqueleto.sha256 são gerados por _esqueleto/sync.py.
"""
import hashlib
import sys
from pathlib import Path


def hash_normalizado(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main() -> None:
    raiz = Path(__file__).resolve().parent.parent
    manifesto = raiz / '_esqueleto.sha256'
    if not manifesto.exists():
        sys.exit(f'Manifesto ausente ({manifesto.name}). '
                 'Rode `python _esqueleto/sync.py` e faça commit do resultado.')

    problemas, conferidos = [], 0
    for linha in manifesto.read_text(encoding='utf-8').splitlines():
        if not linha.strip():
            continue
        esperado, nome = linha.split('  ', 1)
        arquivo = raiz / nome.strip()
        if not arquivo.exists():
            problemas.append(f'{nome.strip()}: arquivo ausente')
            continue
        conferidos += 1
        if hash_normalizado(arquivo) != esperado:
            problemas.append(f'{nome.strip()}: alterado depois do último sync')

    if problemas:
        print('Esqueleto fora de sincronia:')
        for p in problemas:
            print(f'  - {p}')
        sys.exit('Corrija em _esqueleto/ e rode `python _esqueleto/sync.py`; '
                 'não edite a cópia dentro deste repositório.')

    print(f'Esqueleto em dia ({conferidos} arquivos conferidos).')


if __name__ == '__main__':
    main()
