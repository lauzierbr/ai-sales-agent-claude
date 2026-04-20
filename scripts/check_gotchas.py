#!/usr/bin/env python3
"""P10 — Gotcha Registry Linter.

Percorre o código-fonte e detecta padrões problemáticos conhecidos listados
em `docs/GOTCHAS.yaml`. Falha com exit 1 se qualquer padrão for encontrado.

Resolve D5 (retro Sprint 4): gotchas documentados em prose (planner.md)
dependem do Generator "lembrar" de aplicar. Este script torna a verificação
mecânica — roda em pre-commit e no pipeline G3 do smoke gate.

Uso:
    python scripts/check_gotchas.py             # verifica src/ padrão
    python scripts/check_gotchas.py --list      # imprime tabela de gotchas
    python scripts/check_gotchas.py --sprint 4  # mostra só gotchas do sprint N
    python scripts/check_gotchas.py --path output/src/dashboard/  # subdiretório
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERRO: pyyaml não instalado. Rode: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOTCHAS_FILE = REPO_ROOT / "docs" / "GOTCHAS.yaml"
DEFAULT_SEARCH_PATHS = [
    REPO_ROOT / "output" / "src",
]
DEFAULT_EXTENSIONS = {".py", ".html", ".jinja2", ".j2"}


def _load_gotchas() -> list[dict[str, Any]]:
    if not GOTCHAS_FILE.exists():
        print(f"ERRO: {GOTCHAS_FILE} não encontrado.", file=sys.stderr)
        sys.exit(2)
    with open(GOTCHAS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def _matches_glob(path: Path, glob_pattern: str) -> bool:
    """Verifica se um path faz match com um glob pattern relativo ao repo."""
    try:
        rel = path.relative_to(REPO_ROOT)
        return rel.match(glob_pattern)
    except ValueError:
        return False


def _should_skip(path: Path, skip_globs: list[str]) -> bool:
    return any(_matches_glob(path, g) for g in skip_globs)


def _files_to_check(
    search_paths: list[Path], extensions: set[str]
) -> list[Path]:
    files: list[Path] = []
    for base in search_paths:
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            for ext in extensions:
                files.extend(base.rglob(f"*{ext}"))
    return sorted(set(files))


def _check_file(path: Path, gotcha: dict) -> list[tuple[int, str]]:
    """Retorna lista de (lineno, matched_line) para o padrão no arquivo."""
    pattern = re.compile(gotcha["pattern"], re.IGNORECASE)
    matches: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for i, line in enumerate(lines, start=1):
        if pattern.search(line):
            matches.append((i, line.rstrip()))
    return matches


def cmd_check(args: argparse.Namespace) -> int:
    gotchas = _load_gotchas()
    search_paths = [Path(p) for p in args.path] if args.path else DEFAULT_SEARCH_PATHS
    extensions = DEFAULT_EXTENSIONS

    if args.sprint:
        gotchas = [g for g in gotchas if str(g.get("sprint", "")) == str(args.sprint)]
        if not gotchas:
            print(f"Nenhum gotcha registrado para sprint {args.sprint}.")
            return 0

    files = _files_to_check(search_paths, extensions)

    total_violations = 0
    violations_by_gotcha: dict[str, list[tuple[Path, int, str]]] = {}

    for gotcha in gotchas:
        gid = gotcha["id"]
        skip_globs = gotcha.get("skip_files", "")
        if isinstance(skip_globs, str):
            skip_globs = [skip_globs] if skip_globs else []

        for file_path in files:
            if _should_skip(file_path, skip_globs):
                continue
            matches = _check_file(file_path, gotcha)
            for lineno, line in matches:
                violations_by_gotcha.setdefault(gid, [])
                violations_by_gotcha[gid].append((file_path, lineno, line))
                total_violations += 1

    if not violations_by_gotcha:
        print(f"check_gotchas: {len(gotchas)} padrões verificados — nenhuma violação")
        return 0

    print(f"check_gotchas: {total_violations} violação(ões) encontrada(s)\n")
    for gid, hits in violations_by_gotcha.items():
        gotcha = next(g for g in gotchas if g["id"] == gid)
        print(f"[{gid}] {gotcha['description'].strip()[:100]}")
        print(f"  Fix: {gotcha['fix'].strip()[:120]}")
        for file_path, lineno, line in hits:
            rel = file_path.relative_to(REPO_ROOT)
            print(f"  → {rel}:{lineno}: {line[:100]}")
        print()

    return 1


def cmd_list(args: argparse.Namespace) -> int:
    gotchas = _load_gotchas()
    sprint_filter = str(args.sprint) if args.sprint else None
    if sprint_filter:
        gotchas = [g for g in gotchas if str(g.get("sprint", "")) == sprint_filter]

    print(f"\n{'ID':<40} {'Cat':<14} {'Sprint':<7} Descrição")
    print("-" * 100)
    for g in gotchas:
        desc = g.get("description", "").strip().replace("\n", " ")[:55]
        print(
            f"{g['id']:<40} {g.get('category', ''):<14} "
            f"{'S'+str(g.get('sprint','?')):<7} {desc}"
        )
    print()
    return 0


def cmd_markdown_table(args: argparse.Namespace) -> int:
    """Gera tabela markdown para colar em planner.md."""
    gotchas = _load_gotchas()
    print("\n| Área | Gotcha | Workaround obrigatório |")
    print("|------|--------|------------------------|")
    for g in gotchas:
        area = f"`{g['id']}`"
        desc = g.get("description", "").strip().replace("\n", " ")[:80]
        fix = g.get("fix", "").strip().replace("\n", " ")[:80]
        print(f"| {area} | {desc} | {fix} |")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="Lista gotchas registrados")
    parser.add_argument("--markdown", action="store_true", help="Gera tabela markdown")
    parser.add_argument("--sprint", type=int, help="Filtra por sprint")
    parser.add_argument(
        "--path",
        nargs="+",
        help="Diretórios/arquivos a verificar (padrão: output/src/)",
    )
    args = parser.parse_args()

    if args.list:
        return cmd_list(args)
    if args.markdown:
        return cmd_markdown_table(args)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
