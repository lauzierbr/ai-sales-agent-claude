#!/usr/bin/env python3
"""P8 — Evaluator Checkpoint: artefato JSON persistente entre compactações.

Resolve D6 (retro Sprint 4): compactação apaga estado fino do Evaluator.
Após compactação, outra instância não sabe o que já foi verificado —
re-executa checks ou, pior, assume PASS em checks que nunca rodaram.

Este script mantém `artifacts/qa_sprint_N.json` com o estado de cada check.
O Evaluator registra cada check ANTES de marcar como PASS no qa_sprint_N.md;
ao retomar após compactação, lê o JSON e sabe exatamente o que já rodou.

**Fluxo do Evaluator:**

1. Inicia a rodada:
       python scripts/evaluator_checkpoint.py --sprint 5 --round 1 --init

2. Registra cada gate após execução:
       python scripts/evaluator_checkpoint.py --sprint 5 \\
           --check G1_HEALTH --status PASS

       python scripts/evaluator_checkpoint.py --sprint 5 \\
           --check G4_UI_SMOKE --status PASS --log /tmp/smoke_ui.log

       python scripts/evaluator_checkpoint.py --sprint 5 \\
           --check A_MULTITURN --status FAIL --reason "script ausente"

3. Verifica o estado atual (pós-compactação, ao retomar):
       python scripts/evaluator_checkpoint.py --sprint 5 --status
       # Imprime: quais checks rodaram, quais faltam, PASS/FAIL/WARN de cada

4. Copia log para artifacts/:
       python scripts/evaluator_checkpoint.py --sprint 5 \\
           --check G4_UI_SMOKE --attach /tmp/smoke_ui.log

5. Veredicto final:
       python scripts/evaluator_checkpoint.py --sprint 5 --verify
       # Exit 0 se todos os checks requeridos estão PASS.
       # Exit 1 se FAIL ou checks faltantes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO_ROOT / "artifacts"

# Checks requeridos para todo sprint (Onda 1 do harness v2)
REQUIRED_CHECKS = [
    "G1_HEALTH",
    "G2_LINT_IMPORTS",
    "G3_TOOL_COVERAGE",
    "G5_UNIT_TESTS",
    "G6_REGRESSION",
]

# Checks condicionais (requeridos apenas se declarados pelo Planner no spec)
CONDITIONAL_CHECKS = [
    "G4_UI_SMOKE",        # sprint que toca dashboard
    "A_MULTITURN",        # sprint com agente conversacional
    "A_TOOL_COVERAGE",    # sprint com agente conversacional (alias para G3)
    "A_SMOKE",            # staging smoke gate
    "M_INJECT",           # injeção de deps
    "HOMOLOG_PRECONDS",   # verify_homolog_preconditions.py
]

_STATUS_VALS = {"PASS", "FAIL", "WARN", "SKIP"}


def _qa_path(sprint: int) -> Path:
    return ARTIFACTS / f"qa_sprint_{sprint}.json"


def _load(sprint: int) -> dict:
    path = _qa_path(sprint)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save(sprint: int, data: dict) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    _qa_path(sprint).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def cmd_init(args: argparse.Namespace) -> int:
    sprint = args.sprint
    round_ = args.round
    existing = _load(sprint)
    if existing and not args.force:
        print(f"qa_sprint_{sprint}.json já existe. Use --force para reiniciar.")
        return 1
    data = {
        "sprint": sprint,
        "round": round_,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "verdict": None,
        "checks": {},
        "logs": {},
        "required": REQUIRED_CHECKS[:],
        "conditional": [],
    }
    _save(sprint, data)
    print(f"[init] qa_sprint_{sprint}.json criado (round={round_})")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    sprint = args.sprint
    data = _load(sprint)
    if not data:
        print(f"[erro] qa_sprint_{sprint}.json não encontrado. Rode --init primeiro.")
        return 1

    status = args.status.upper()
    if status not in _STATUS_VALS:
        print(f"[erro] --status deve ser um de: {_STATUS_VALS}")
        return 1

    entry: dict = {
        "status": status,
        "ran": status != "SKIP",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if args.reason:
        entry["reason"] = args.reason
    if args.log:
        log_path = Path(args.log)
        if log_path.exists():
            dest = ARTIFACTS / log_path.name
            shutil.copy2(log_path, dest)
            entry["log"] = log_path.name
            print(f"[log] copiado → artifacts/{log_path.name}")
        else:
            entry["log_missing"] = str(args.log)

    data["checks"][args.check] = entry
    _save(sprint, data)

    emoji = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "SKIP": "—"}.get(status, "?")
    print(f"[{emoji}] {args.check} → {status}")
    return 0


def cmd_attach(args: argparse.Namespace) -> int:
    sprint = args.sprint
    data = _load(sprint)
    if not data:
        print(f"[erro] qa_sprint_{sprint}.json não encontrado.")
        return 1
    log_path = Path(args.log)
    if not log_path.exists():
        print(f"[erro] arquivo não encontrado: {log_path}")
        return 1
    dest = ARTIFACTS / log_path.name
    shutil.copy2(log_path, dest)
    check = data["checks"].get(args.check, {})
    check["log"] = log_path.name
    data["checks"][args.check] = check
    _save(sprint, data)
    print(f"[attach] {log_path.name} → artifacts/{log_path.name}")
    return 0


def cmd_add_conditional(args: argparse.Namespace) -> int:
    sprint = args.sprint
    data = _load(sprint)
    if not data:
        print(f"[erro] qa_sprint_{sprint}.json não encontrado.")
        return 1
    cond = data.setdefault("conditional", [])
    for c in args.checks:
        if c not in cond:
            cond.append(c)
    _save(sprint, data)
    print(f"[require] checks condicionais adicionados: {args.checks}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    sprint = args.sprint
    data = _load(sprint)
    if not data:
        print(f"qa_sprint_{sprint}.json não encontrado.")
        return 1

    required = data.get("required", REQUIRED_CHECKS)
    conditional = data.get("conditional", [])
    all_required = list(dict.fromkeys(required + conditional))
    checks = data.get("checks", {})

    print(f"\n=== qa_sprint_{sprint}.json (round {data.get('round')}) ===")
    print(f"Iniciado: {data.get('started_at', '?')}")
    print(f"Veredicto: {data.get('verdict', 'pendente')}")
    print()

    failed = []
    missing = []
    for check_id in all_required:
        entry = checks.get(check_id)
        if entry is None:
            missing.append(check_id)
            print(f"  [ MISSING ] {check_id}")
        else:
            s = entry.get("status", "?")
            log = entry.get("log", "")
            note = f" — log: {log}" if log else ""
            reason = entry.get("reason", "")
            note += f" — {reason}" if reason else ""
            emoji = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "SKIP": "—"}.get(s, "?")
            print(f"  [{emoji} {s:4}] {check_id}{note}")
            if s == "FAIL":
                failed.append(check_id)

    # Checks executados mas não requeridos
    extras = [c for c in checks if c not in all_required]
    if extras:
        print(f"\n  Extra (não requeridos):")
        for c in extras:
            s = checks[c].get("status", "?")
            print(f"  [  {s:4}] {c}")

    print()
    if failed or missing:
        print(f"FAIL: {len(failed)} falha(s), {len(missing)} check(s) ausente(s)")
        return 1
    print("PASS: todos os checks requeridos concluídos")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    rc = cmd_status(args)
    sprint = args.sprint
    data = _load(sprint)
    if not data:
        return 1

    if rc == 0:
        data["verdict"] = "APROVADO"
        data["verdict_at"] = datetime.now(timezone.utc).isoformat()
        _save(sprint, data)
        print(f"\n[verdict] APROVADO → qa_sprint_{sprint}.json atualizado")
    else:
        data["verdict"] = "REPROVADO"
        data["verdict_at"] = datetime.now(timezone.utc).isoformat()
        _save(sprint, data)
        print(f"\n[verdict] REPROVADO → qa_sprint_{sprint}.json atualizado")

    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sprint", "-s", type=int, required=True)
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", aliases=["--init"])
    p_init.add_argument("--round", type=int, default=1)
    p_init.add_argument("--force", action="store_true")

    p_check = sub.add_parser("check", aliases=["--check"])
    p_check.add_argument("check_id")
    p_check.add_argument("--status", required=True)
    p_check.add_argument("--log", default=None)
    p_check.add_argument("--reason", default=None)

    p_attach = sub.add_parser("attach", aliases=["--attach"])
    p_attach.add_argument("check_id")
    p_attach.add_argument("--log", required=True)

    p_require = sub.add_parser("require")
    p_require.add_argument("checks", nargs="+")

    sub.add_parser("status", aliases=["--status"])
    sub.add_parser("verify", aliases=["--verify"])

    args, unknown = parser.parse_known_args()

    # Suporte a invocação inline: --init, --check ID --status X, --status, --verify
    if args.cmd is None:
        if "--init" in unknown:
            args.cmd = "init"
            args.round = 1
            args.force = "--force" in unknown
        elif "--status" in unknown and "--check" not in unknown:
            args.cmd = "status"
        elif "--verify" in unknown:
            args.cmd = "verify"
        elif "--check" in unknown:
            idx = unknown.index("--check")
            args.cmd = "check"
            args.check_id = unknown[idx + 1] if idx + 1 < len(unknown) else ""
            args.status = unknown[unknown.index("--status") + 1] if "--status" in unknown else "PASS"
            args.log = unknown[unknown.index("--log") + 1] if "--log" in unknown else None
            args.reason = unknown[unknown.index("--reason") + 1] if "--reason" in unknown else None

    dispatch = {
        "init": lambda: cmd_init(args),
        "--init": lambda: cmd_init(args),
        "check": lambda: _cmd_check_inline(args),
        "--check": lambda: _cmd_check_inline(args),
        "attach": lambda: _cmd_attach_inline(args),
        "--attach": lambda: _cmd_attach_inline(args),
        "require": lambda: cmd_add_conditional(args),
        "status": lambda: cmd_status(args),
        "--status": lambda: cmd_status(args),
        "verify": lambda: cmd_verify(args),
        "--verify": lambda: cmd_verify(args),
    }

    fn = dispatch.get(args.cmd)
    if fn is None:
        parser.print_help()
        return 1
    return fn()


def _cmd_check_inline(args: argparse.Namespace) -> int:
    if hasattr(args, "check_id"):
        args.check = args.check_id
    return cmd_check(args)


def _cmd_attach_inline(args: argparse.Namespace) -> int:
    if hasattr(args, "check_id"):
        args.check = args.check_id
    return cmd_attach(args)


if __name__ == "__main__":
    sys.exit(main())
