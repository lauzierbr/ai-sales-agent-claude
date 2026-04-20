#!/usr/bin/env python3
"""Homologation Precondition Validator (P4 do harness v2).

Lê um arquivo de homologação (`docs/exec-plans/active/homologacao_sprint_N.md`),
extrai SQLs de precondição e executa cada uma contra o banco staging.
Falha com exit 1 se qualquer SQL não retornar ao menos 1 linha ou lançar erro.

Resolve: no Sprint 4, os cenários H4 (pedidos com >30 dias) e H7
(cliente 5519992066177) foram descobertos *durante* a homologação manual
com precondições erradas no banco. Esse script pega isso antes de o humano
abrir o WhatsApp.

**Formato esperado na tabela de homologação** (em `planner.md`):

    | ID | Cenário | SQL precondição | Esperado |
    |----|---------|-----------------|----------|
    | H4 | Clientes inativos | `SELECT count(*) FROM pedidos WHERE criado_em < NOW() - INTERVAL '30 days' AND tenant_id='jmb';` | count>0 |

Regras de avaliação:
  - Se a query retornar 0 linhas → FAIL.
  - Se a query for `SELECT count(...) AS n FROM ...` e `n == 0` → FAIL.
  - Se a query lançar erro SQL → FAIL.
  - Caso contrário → PASS.

Uso:
    infisical run --env=staging -- \\
      python scripts/verify_homolog_preconditions.py \\
        --file docs/exec-plans/active/homologacao_sprint_5.md

    python scripts/verify_homolog_preconditions.py --file <path> --sprint 5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

try:
    import asyncpg
except ImportError:
    print("ERRO: asyncpg não instalado. Rode com o venv do projeto.", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent


class Precondicao(NamedTuple):
    id: str
    cenario: str
    sql: str


_TABLE_ROW_RE = re.compile(r"^\|\s*(H\d+|B\d+)\s*\|(.+)$")


def _extract_sql_from_cell(cell: str) -> str | None:
    """Retira SQL de dentro de uma célula markdown (entre backticks ou cru)."""
    cell = cell.strip()
    if not cell or cell in {"-", "—", "n/a", "N/A"}:
        return None
    # Backticks de código inline: `SELECT ...`
    m = re.search(r"`([^`]+)`", cell)
    if m:
        sql = m.group(1).strip()
    else:
        sql = cell
    if not re.search(r"\b(select|with)\b", sql, re.IGNORECASE):
        return None
    return sql


def parse_homolog_file(path: Path) -> list[Precondicao]:
    """Extrai precondições das tabelas markdown.

    Procura por tabelas com cabeçalho contendo "SQL" (case-insensitive).
    Para cada linha `| Hn | cenario | sql | ...|`, devolve Precondicao.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    preconds: list[Precondicao] = []
    sql_col_idx: int | None = None

    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            sql_col_idx = None
            continue

        # Detecta header: tem "SQL" em alguma coluna, próxima linha é separador
        if sql_col_idx is None:
            if re.search(r"\bsql\b", line, re.IGNORECASE) and (
                i + 1 < len(lines) and re.match(r"^\s*\|[\s\-|]+\|\s*$", lines[i + 1])
            ):
                cols = [c.strip().lower() for c in line.strip().strip("|").split("|")]
                for idx, c in enumerate(cols):
                    if "sql" in c:
                        sql_col_idx = idx
                        break
            continue

        # Já estamos numa tabela com SQL identificada
        m = _TABLE_ROW_RE.match(line.strip())
        if not m:
            continue

        row_id = m.group(1)
        rest = m.group(2)
        cols = [c.strip() for c in rest.split("|")]
        # cols[0] é cenario, cols[sql_col_idx-1] é SQL (offset porque id é col 0)
        sql_idx = sql_col_idx - 1
        if sql_idx < 0 or sql_idx >= len(cols):
            continue
        sql = _extract_sql_from_cell(cols[sql_idx])
        if sql is None:
            continue
        cenario = cols[0] if cols else ""
        preconds.append(Precondicao(id=row_id, cenario=cenario, sql=sql))

    return preconds


def _is_count_zero(row: asyncpg.Record) -> bool:
    """Detecta SELECT count() com resultado 0."""
    if not row:
        return False
    # Se há exatamente uma coluna e o valor é 0 → tratar como FAIL
    values = list(row.values())
    if len(values) == 1 and isinstance(values[0], int) and values[0] == 0:
        return True
    return False


async def _run_sql(conn: asyncpg.Connection, sql: str) -> tuple[bool, str]:
    """Executa SQL e decide PASS/FAIL + mensagem."""
    try:
        rows = await conn.fetch(sql)
    except Exception as exc:
        return False, f"erro SQL: {exc}"
    if not rows:
        return False, "0 linhas retornadas"
    if _is_count_zero(rows[0]):
        return False, "count(*) = 0"
    return True, f"{len(rows)} linha(s); 1ª: {dict(rows[0])}"


async def _main_async(path: Path) -> int:
    preconds = parse_homolog_file(path)
    if not preconds:
        print(f"AVISO: nenhuma SQL de precondição encontrada em {path}", file=sys.stderr)
        print(
            "Adicione uma coluna 'SQL precondição' na tabela de cenários "
            "(ver docstring do script).",
            file=sys.stderr,
        )
        return 0

    pg_url = os.getenv("POSTGRES_URL", "")
    if not pg_url:
        print("ERRO: POSTGRES_URL não definida.", file=sys.stderr)
        return 2
    # asyncpg não aceita o driver suffix do SQLAlchemy
    pg_url_raw = pg_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgres://"
    )

    print(f"Validando {len(preconds)} precondição(ões) de {path.name}...")
    print()

    conn = await asyncpg.connect(pg_url_raw)
    try:
        passed = 0
        failed = 0
        failures: list[tuple[str, str]] = []
        for p in preconds:
            ok, msg = await _run_sql(conn, p.sql)
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {p.id} — {p.cenario[:60]}")
            print(f"         SQL: {p.sql[:120]}{'...' if len(p.sql) > 120 else ''}")
            print(f"         {msg}")
            if ok:
                passed += 1
            else:
                failed += 1
                failures.append((p.id, msg))
    finally:
        await conn.close()

    print()
    print(f"=== {passed}/{passed + failed} precondições OK ===")
    if failed:
        print()
        print("Cenários que não podem ser homologados:")
        for id_, msg in failures:
            print(f"  - {id_}: {msg}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        help="Caminho do homologacao_sprint_N.md. Se omitido, procura ativos.",
    )
    parser.add_argument(
        "--sprint",
        "-s",
        type=int,
        help="Número do sprint (usa docs/exec-plans/active/homologacao_sprint_N.md).",
    )
    args = parser.parse_args()

    path: Path | None = args.file
    if path is None and args.sprint is not None:
        path = REPO_ROOT / "docs" / "exec-plans" / "active" / f"homologacao_sprint_{args.sprint}.md"
    if path is None:
        actives = sorted((REPO_ROOT / "docs" / "exec-plans" / "active").glob("homologacao_sprint_*.md"))
        if not actives:
            print(
                "ERRO: especifique --file ou --sprint. Nenhum homologacao_sprint_N.md ativo.",
                file=sys.stderr,
            )
            return 2
        path = actives[-1]
        print(f"Usando arquivo mais recente em active/: {path.name}")

    if not path.exists():
        print(f"ERRO: arquivo não encontrado: {path}", file=sys.stderr)
        return 2

    return asyncio.run(_main_async(path))


if __name__ == "__main__":
    sys.exit(main())
