# D030 — ERP Adapter pattern + canonical contact ownership no app

**Status:** Proposto (2026-04-29)
**Decisão de:** Lauzier (PO/Tech Lead) e Claude (arquitetura)
**Substitui:** Reflete uma escolha estrutural ainda não formalizada nos sprints anteriores
**Relacionado a:** F-04 (modelagem cliente×contato), B-27 (showstopper), Sprint 8 EFOS, futuro Sprint Bling

---

## Contexto

O produto AI Sales Agent precisa funcionar com **múltiplos canais** (hoje WhatsApp,
amanhã Telegram, voz) e **múltiplos ERPs** (hoje EFOS via backup SSH, alvo Bling
via API REST, futuros: Tiny, Omie, e ERPs proprietários de cada distribuidora).

Cada cliente B2B (pessoa jurídica) tem na prática **N pessoas físicas** que
interagem com o bot:
- O dono manda áudio às vezes
- O comprador faz pedidos no dia-a-dia
- A gerente cobra status de entrega
- Cada um com **número de WhatsApp diferente**

A pergunta que originou este documento foi:
**"Quem é o source of truth para os contatos de comunicação?"**

ERPs atuais lidam com isso de formas heterogêneas:

| ERP | Modelo de contato |
|-----|-------------------|
| EFOS | 1 contato embutido em `tb_clientes` (`cl_contato`, `cl_telefone`). 78% vazios. Sem API moderna. |
| Bling | Array `pessoasContato[]` (N por cliente) + `tiposContato[]` para categorização. API REST OAuth 2.0. |
| Tiny | Modelo similar a Bling com array de contatos (não validado em detalhe). |
| ERPs custom | Variável — alguns têm planilha Excel exportada. |

Se delegarmos 100% ao ERP, ficamos limitados pelo menor denominador comum (EFOS:
1 contato por cliente). Se assumirmos tudo no app, perdemos sync com cadastro
oficial. A decisão é onde traçar a linha.

---

## Decisão

Adotamos um modelo **híbrido de bounded contexts** com clara divisão de
ownership e um **adapter pattern (hexagonal)** para abstrair os ERPs:

### App é source of truth para

| Domínio | Justificativa |
|---------|---------------|
| **Identidades de canal** (telefone WhatsApp, Telegram chat_id, voice peer_id) | Só sabemos que `+5519999097001` é a Cris porque ela falou com o BOT. Esse fato emerge do uso do app, não do cadastro fiscal. |
| **Mapeamento canal → cliente** (qual contato pertence a qual PJ) | Decisão operacional do gestor JMB ("essa Cris é compradora da Drogaria Calderari"), não cadastro fiscal. |
| **Permissões** (quem pode comprar em nome de quem, limites por contato) | Política de negócio do tenant, não do ERP. |
| **Histórico de conversas e feedback** | Próprio app gera. |
| **Pedidos placed via bot** (write model `pedidos`) | App é dono enquanto não confirmados no ERP. |

### ERP é source of truth para

| Domínio | Justificativa |
|---------|---------------|
| **Identidade fiscal/cadastral** (CNPJ, razão social, IE, endereço) | Cadastro oficial, sujeito a auditoria fiscal. |
| **Situação cadastral** (ativo/inativo/inadimplente) | Decisão financeira do ERP (limite de crédito, score). |
| **Catálogo** (produtos, preços, estoque) | Nem todo produto vendível pelo bot; ERP define disponibilidade. |
| **Histórico financeiro consolidado** | Pedidos confirmados, NF emitidas, recebimentos — compliance fiscal. |
| **Vendedor responsável pelo cliente** | Comissão e carteira são contabilizadas pelo ERP. |

### Como modelar a sobreposição (contato como pessoa)

Hoje EFOS tem `cl_contato` (1 nome). Bling tem array. Resolvemos com:

```
commerce_accounts (read-only do ERP)
  external_id, cnpj, razão_social, situação, vendedor_codigo, ...
  + suggested_contacts[]   ← deserializado do ERP quando disponível
                              (cl_contato no EFOS, pessoasContato[] no Bling)

contacts (write model do app)
  id, tenant_id, account_external_id → commerce_accounts.external_id
  nome (PF), papel (comprador/dono/gerente), authorized: bool
  channels[]: { kind: whatsapp|telegram, identifier: "+5519...", verified: bool }
  origin: 'erp_suggested' | 'manual' | 'self_registered'
  last_active_at, criado_em
```

**Fluxos:**

1. **Cliente novo aparece no ERP:** sync importa `commerce_accounts` (PJ).
   Contatos sugeridos do ERP são salvos em `account.suggested_contacts[]` —
   **não viram `contacts` automaticamente**. Gestor ainda precisa confirmar
   ("essa pessoa é mesmo o comprador autorizado?").

2. **Mensagem WhatsApp de número desconhecido:** app cria `contact` com
   `origin='self_registered'` e `authorized=False`. Bot pede ao gestor:
   "+5519... mandou mensagem dizendo que é da Drogaria Calderari. Autorizo?"

3. **Gestor cadastra contato via dashboard:** INSERT em `contacts` com
   `origin='manual'`, vinculando a `account.external_id`. Não toca em
   `clientes_b2b` (que será deprecada — ver D031 a propor).

4. **Sync inverso para Bling (futuro):** app pode publicar `contacts` recém-criados
   de volta para `pessoasContato[]` no Bling via `BlingAdapter.push_contact()`.
   Para EFOS este caminho é noop (sem API write).

### Adapter pattern (hexagonal)

```
output/src/integrations/
├── ports/
│   └── erp.py                  # Interface ERPAdapter (Protocol)
└── connectors/
    ├── efos_backup/            # implementação atual (read-only via pg_restore)
    ├── bling/                  # próximo a implementar (REST + OAuth2 + write)
    └── tiny/                   # futuro
```

**Interface ERPAdapter:**

```python
class ERPAdapter(Protocol):
    """Contrato uniforme para qualquer ERP. Cada método é opcional —
    adapters declaram capabilities para o app saber o que está disponível."""

    capabilities: set[ERPCapability]
    # Ex: {READ_ACCOUNTS, READ_ORDERS, READ_INVENTORY,
    #      WRITE_CONTACTS, WRITE_ORDERS, WEBHOOK_EVENTS}

    async def list_accounts(self, since: datetime | None) -> list[Account]: ...
    async def get_account(self, external_id: str) -> Account | None: ...
    async def list_orders(self, account_id: str, period: Period) -> list[Order]: ...

    # Opcionais — só se capability declarada
    async def push_contact(self, account_id: str, contact: Contact) -> str: ...
    async def push_order(self, order: Order) -> str: ...
    async def subscribe_webhooks(self, callback_url: str) -> None: ...
```

**Trocar de ERP** = trocar config do tenant para usar outro adapter. Domain
core (`commerce/`, `agents/`, `dashboard/`) não muda.

---

## Análise comparativa de capabilities

| Capability | EFOS Backup | Bling API v3 | Tiny API |
|-----------|-------------|--------------|----------|
| READ_ACCOUNTS | ✅ via dump | ✅ GET /contatos | ✅ |
| READ_ORDERS | ✅ via dump | ✅ GET /pedidos/vendas | ✅ |
| READ_INVENTORY | ✅ via dump | ✅ GET /estoques | ✅ |
| MULTIPLE_CONTACTS_PER_ACCOUNT | ❌ (1 embutido) | ✅ `pessoasContato[]` | ✅ |
| WRITE_CONTACTS | ❌ (read-only) | ✅ POST /contatos | ✅ |
| WRITE_ORDERS | ❌ | ✅ POST /pedidos/vendas | ✅ |
| WEBHOOK_EVENTS | ❌ (polling diário) | ✅ webhooks REST | ✅ |
| Sync latency | 24h (backup diário) | seconds (webhooks) | seconds |
| Auth | SSH key + password | OAuth 2.0 | API token |

**Implicações estratégicas:**

1. **Bling é claramente superior tecnicamente** — webhooks, write capabilities,
   modelo de contato rico. EFOS é fim-de-vida arquitetural.

2. **Migrar para Bling é viável sem refatorar app:** trocar
   `EfosBackupAdapter` por `BlingAdapter` no config do tenant. Domain code
   intocado.

3. **Janela de sync:** com EFOS, dados estão até 24h desatualizados. Com
   Bling, near-real-time via webhooks. Isso muda a UX (ex: "estoque agora"
   vira possível).

4. **`contacts` no app fica robusto a qualquer ERP:** se Bling oferece
   pessoasContato, app sincroniza; se EFOS oferece só `cl_contato`, app
   importa como sugestão. Modelo do app é o canônico.

---

## Consequências

### Positivas

- **Migração de ERP é localizada** (1 adapter, não rewrites). Reduz lock-in.
- **Modelo de contato rico mesmo com ERP pobre** — não somos limitados pelo EFOS.
- **App pode evoluir multi-canal** sem mudar ERP (Telegram/voice como novos
  `channels[]` em `contacts`).
- **Compliance LGPD mais limpo** — contatos vivem no app, podemos auditar e
  apagar sem coordenar com ERP externo.
- **Suporte natural a múltiplos compradores por cliente** — caso comum em
  supermercados (responsável compras + gerente + dono).

### Negativas

- **Mais complexidade no início** — porting EFOS para o adapter pattern + criar
  Bling adapter. Estimo 1.5–2 sprints para formalizar.
- **Risco de drift** entre `account.suggested_contacts[]` e `contacts` —
  mitigação: dashboard mostra ambos, gestor escolhe.
- **Sincronização de pedidos com Bling é write-back** — error handling
  importa (retry, idempotência via external_reference).

### Migrações implícitas

- **Migration nova:** tabela `contacts` (campos descritos acima)
- **Migration nova:** `commerce_accounts_b2b` ganha `suggested_contacts JSONB`,
  `nome_fantasia`, `telefone`, `email` (campos perdidos no Sprint 8)
- **Deprecar `clientes_b2b`** — propor em ADR D031 separado. Provável caminho:
  manter por compatibilidade até Sprint X+2, migrar dados para `contacts`,
  depois remover.

---

## Roadmap recomendado

### Sprint 10 (próximo) — Hotfixes críticos + foundations

1. Corrigir B-26 (truncação histórico — crítico)
2. Corrigir B-27 (cadastro contato showstopper) — **com nova tabela `contacts`
   já no padrão D030**, não como UPDATE em `clientes_b2b`
3. Corrigir B-23 (áudio Whisper)
4. Corrigir B-24 (system prompt áudio)

### Sprint 11 — Bling adapter (read-only)

1. Implementar `output/src/integrations/connectors/bling/`
2. Capability READ_ACCOUNTS, READ_ORDERS, READ_INVENTORY via OAuth 2.0
3. Tenant config: escolher entre `efos_backup` e `bling` por tenant
4. Migrar JMB para Bling em paralelo (manter EFOS rodando como backup
   durante 1 sprint)

### Sprint 12 — Bling write + webhooks

1. WRITE_CONTACTS — push de `contacts` para `pessoasContato[]` Bling
2. WRITE_ORDERS — push de pedidos do bot para Bling (com idempotência)
3. WEBHOOK_EVENTS — receber updates real-time

### Sprint 13+ — Multi-canal

1. Telegram adapter (canal novo, não ERP)
2. Estrutura `contacts.channels[]` JSONB já preparada para isso

---

## Decisões pendentes (para PO confirmar)

1. **Confirmar Bling como ERP alvo principal** (vs Tiny ou outro)
2. **Janela de migração JMB:** Sprint 11 paralelo ou Sprint 12+ depois de
   estabilizar bot?
3. **`clientes_b2b` legacy** — deprecar quando? Quem migra os 5 contatos
   atuais?

---

## Referências

- [Bling API v3 — Criar contato](https://docs.floui.io/guia/conectores/categorias/servicos-externos/bling-erp-bling-api-v3/contatos/criar-contato)
- [Bling Developer Portal](https://developer.bling.com.br/referencia)
- [Multi-tenant SaaS architecture (WorkOS)](https://workos.com/blog/developers-guide-saas-multi-tenant-architecture)
- F-04 (BACKLOG.md) — modelagem cliente×contato (substituído por este ADR)
- B-27 — showstopper que motivou a investigação
