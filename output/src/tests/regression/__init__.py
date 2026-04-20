"""Regression tests — um teste por bug histórico.

Cada bug encontrado em homologação humana vira um teste aqui. Eles passam
no estado atual do código (o fix já foi aplicado) e servem de baseline
permanente: se alguém regredir, o teste fica vermelho.

Convenção: `test_sprint_N_bugs.py` agrupa os bugs B1..Bk daquele sprint
registrados em `docs/exec-plans/completed/homologacao_sprint_N.md`.
"""
