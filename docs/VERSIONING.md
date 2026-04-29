# Versionamento — AI Sales Agent

Convenção de versão e processo de release para staging.

---

## Convenção

```
v0.{SPRINT}.{HOTFIX}
```

| Parte | Significado |
|-------|-------------|
| `0`   | Major fixo enquanto produto estiver em piloto. Vira `1` quando primeira versão de produção for cortada. |
| `SPRINT` | Número do sprint que originou esta versão (ex: 9 = Sprint 9). |
| `HOTFIX` | Contador incremental dentro do sprint. `0` = entrega inicial do sprint. `1+` = hotfixes/iterações sobre o mesmo sprint. |

### Exemplos

| Versão | Significado |
|--------|-------------|
| `v0.9.0` | Entrega inicial do Sprint 9 |
| `v0.9.1` | Primeiro hotfix do Sprint 9 (correção SQL columns commerce_*) |
| `v0.9.2` | Segundo hotfix do Sprint 9 (se houver) |
| `v0.10.0` | Entrega inicial do Sprint 10 |
| `v1.0.0` | Primeira versão de produção (depois do piloto JMB validar) |

### Quando bumpar HOTFIX vs SPRINT

- **Bumpar HOTFIX (Y → Y+1):** correções de bugs descobertos após o sprint estar
  em staging, que NÃO mudam o escopo aprovado do sprint. Ex: B-26, B-27 são
  hotfixes do Sprint 9 → criariam `v0.9.2`, `v0.9.3`...

- **Bumpar SPRINT (X → X+1):** ao iniciar implementação de um novo sprint
  conforme `artifacts/spec.md` aprovado. O Generator deve bumpar
  `output/src/__init__.py` para `v0.{X+1}.0` no primeiro commit do sprint.

---

## Processo automatizado

A versão vive em **um único lugar**: `output/src/__init__.py` como `__version__`.

```python
# output/src/__init__.py
__version__ = "0.9.1"
```

Esse valor é importado por:
- `output/src/main.py` — usado no log de startup, no FastAPI metadata e no
  endpoint `/health`
- `output/src/dashboard/ui.py` — exposto como `app_version` global no Jinja,
  renderizado discretamente ao lado do título no `base.html`

### Auto-tag no deploy

`scripts/deploy.sh` cria automaticamente a tag git no commit deployado quando
`ENV == "staging"`:

```bash
./scripts/deploy.sh staging main
# → após health check OK, lê __version__, cria tag v0.X.Y, push origin
```

Comportamento da auto-tag:

- Se a tag não existe → cria e faz push
- Se a tag já existe **no mesmo commit** → noop (idempotente)
- Se a tag já existe **em commit diferente** → alerta e NÃO sobrescreve
  (sinal claro: bump `__version__` antes de commitar/deployar)

---

## Processo do Generator

Ao iniciar implementação de um sprint:

1. Bumpar `output/src/__init__.py` para `__version__ = "0.{N}.0"` onde N = sprint
2. Commit dedicado: `chore(version): bump v0.{N}.0 — Sprint {N} inicial`
3. Implementar entregas do contrato
4. Antes de deploy, confirmar que `grep '__version__' output/src/__init__.py`
   retorna a versão correta

Para hotfix:

1. Bumpar `__version__` para `0.{N}.{Y+1}` (Y+1 = próximo hotfix dentro do sprint)
2. Commit: `chore(version): bump v0.{N}.{Y+1} — hotfix <descrição>`
3. Continuar com a correção

---

## Histórico

| Tag | Sprint | Conteúdo |
|-----|--------|----------|
| v0.6.1 | Sprint 6 | Pre-pilot hardening |
| v0.7.0 | Sprint 7 | Notificação gestor |
| v0.8.0 | Sprint 8 | Hotfixes piloto + integração EFOS via backup |
| v0.9.0 | Sprint 9 | Commerce reads + dashboard sync + áudio Whisper |
| v0.9.1 | Sprint 9 | Hotfix SQL commerce_*, JOIN nomes faltantes |

---

## Visualização da versão

A versão deployada é visível em:

1. **Dashboard:** discreta ao lado do título "AI Sales Agent" no header de
   navegação (componente `base.html`, classe CSS `.nav-version`)
2. **Health endpoint:** `GET /health` → `{"version": "0.9.1", ...}`
3. **Log de startup:** `app_iniciada versao=0.9.1`
4. **Git tags:** `git tag -l "v*"` lista o histórico completo

---

## Quando vamos para produção

Quando o piloto JMB for validado e o produto entrar em produção real:

1. Major bump para `1.0.0`
2. Convenção SemVer padrão (`MAJOR.MINOR.PATCH`):
   - PATCH = hotfix sem mudança de comportamento
   - MINOR = features novas backward-compatible
   - MAJOR = breaking changes
3. Tags com prefixo `v` continuam (`v1.0.0`, `v1.0.1`, ...)
4. Pode haver branches de release (`release/1.0`) se houver paralelismo

Por enquanto (piloto), a convenção `v0.{SPRINT}.{HOTFIX}` é mais útil porque
amarra cada release ao trabalho de produto realizado.
