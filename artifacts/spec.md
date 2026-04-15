# Sprint 2 — Agente Cliente Completo

**Status:** Em planejamento
**Data:** 2026-04-15
**Pré-requisitos:** Sprint 1 concluído — FastAPI com TenantProvider, JWT, webhook Evolution API, scheduler, v0.2.0 tagueada

---

## Objetivo

Ao final deste sprint, o sistema possui um agente conversacional real usando o Claude SDK que identifica o cliente B2B pelo número de telefone, mantém histórico de conversa (Redis + PostgreSQL), consulta o catálogo de produtos via busca semântica, e registra pedidos confirmados gerando um PDF e notificando o gestor via WhatsApp.

---

## Contexto

Sprint 1 entregou o esqueleto: IdentityRouter stub (sempre DESCONHECIDO), AgentCliente com resposta de template fixo, webhook funcional. Nenhuma conversa real ocorre — o agente não usa IA, não identifica clientes e não processa pedidos.

Sprint 2 completa o núcleo do produto: o cliente envia uma mensagem, o sistema identifica quem é, o Claude conduz a conversa, e pedidos confirmados geram documentos e notificam o gestor. O MVP está funcional após este sprint.

**Remoções deliberadas (decisão do usuário):**
- Loja Integrada API — fora do MVP
- resolve_preco() com preços diferenciados — fora do MVP
- Evaluator em produção — equívoco; Evaluator é exclusivo do harness de desenvolvimento

**Decisão arquitetural D023:** pedido confirmado gera PDF + notificação WhatsApp para o gestor. Processamento manual no EFOS. Sem integração ERP para escrita de pedidos no MVP.

ADR D023 será registrado em `docs/design-docs/index.md` após aprovação do contrato.

---

## Domínios e camadas afetadas

| Domínio | Camadas |
|---------|---------|
| agents | Types, Config, Repo, Service, Runtime (reescritas), UI (atualização) |
| orders | Types, Config, Repo, Service, Runtime — domínio novo completo |
| alembic | Migrations 0007–0012 |
| pyproject.toml | adicionar fpdf2>=2.7.0 |
| main.py | lifespan: mkdir pdfs; montar /pdfs como StaticFiles |

---

## Considerações multi-tenant

Todas as novas tabelas seguem o padrão D020: `tenant_id TEXT NOT NULL` com FK para `tenants(id)`. Todos os métodos públicos de Repo recebem `tenant_id: str`. ConversaRepo usa chaves Redis prefixadas por `conv:{tenant_id}:{telefone}`.

---

## Estado das migrations

Migrations 0007–0012 já criadas (produzidas antes do Generator Fase 1 por engano — Generator Fase 2 não precisa recriá-las, apenas verificar consistência com este spec).

---

## Entregas

### E1 — Migrations 0007–0012

**Arquivos (já criados):**
- `output/alembic/versions/0007_clientes_b2b.py`
- `output/alembic/versions/0008_representantes.py`
- `output/alembic/versions/0009_conversas.py`
- `output/alembic/versions/0010_mensagens_conversa.py`
- `output/alembic/versions/0011_pedidos.py`
- `output/alembic/versions/0012_itens_pedido.py`

**Schema:**

`clientes_b2b`: id, tenant_id (FK→tenants CASCADE), nome, cnpj, telefone, ativo, criado_em
- UNIQUE(tenant_id, cnpj), UNIQUE(tenant_id, telefone)
- INDEX: (tenant_id), (tenant_id, telefone)

`representantes`: id, tenant_id (FK→tenants CASCADE), usuario_id (FK→usuarios SET NULL, nullable), telefone, nome, ativo
- UNIQUE(tenant_id, telefone)
- INDEX: (tenant_id), (tenant_id, telefone)

`conversas`: id, tenant_id (FK→tenants CASCADE), telefone, persona (CHECK IN 'cliente_b2b','representante','desconhecido'), iniciada_em, encerrada_em (nullable)
- INDEX: (tenant_id, telefone), (tenant_id, iniciada_em)

`mensagens_conversa`: id, conversa_id (FK→conversas CASCADE), role (CHECK IN 'user','assistant'), conteudo, criado_em
- INDEX: (conversa_id), (conversa_id, criado_em)

`pedidos`: id, tenant_id (FK→tenants CASCADE), cliente_b2b_id (FK→clientes_b2b SET NULL, nullable), representante_id (FK→representantes SET NULL, nullable), status (CHECK IN 'pendente','confirmado','cancelado', default 'pendente'), total_estimado NUMERIC(12,2), pdf_path (nullable), criado_em
- INDEX: (tenant_id), (tenant_id, status), (tenant_id, criado_em)

`itens_pedido`: id, pedido_id (FK→pedidos CASCADE), produto_id (FK→produtos RESTRICT), codigo_externo, nome_produto, quantidade (CHECK > 0), preco_unitario NUMERIC(12,2) (CHECK >= 0), subtotal NUMERIC(12,2)
- INDEX: (pedido_id)
- Nota: subtotal calculado em Python (não gerado no banco — evita gotcha SQLAlchemy Computed)

**Critérios:**
- [ ] Cada migration tem `revision`, `down_revision`, `upgrade()`, `downgrade()` corretos
- [ ] `alembic upgrade head` aplica todas sem erro no dev
- [ ] `alembic downgrade -1` desfaz cada migration sem erro

---

### E2 — Novos tipos (agents + orders)

**Arquivos:**
- `output/src/agents/types.py` — adicionar ao existente: `ClienteB2B`, `Representante`, `Conversa`, `MensagemConversa`, `ItemIntento`, `IntentoPedido`
- `output/src/orders/__init__.py` — já existe (vazio)
- `output/src/orders/types.py` — criar: `StatusPedido`, `ItemPedidoInput`, `ItemPedido`, `CriarPedidoInput`, `Pedido`

**Modelos agents/types.py a adicionar:**
```python
class ClienteB2B(BaseModel):
    id: str; tenant_id: str; nome: str; cnpj: str; telefone: str; ativo: bool; criado_em: datetime

class Representante(BaseModel):
    id: str; tenant_id: str; usuario_id: str | None; telefone: str; nome: str; ativo: bool

class Conversa(BaseModel):
    id: str; tenant_id: str; telefone: str; persona: Persona; iniciada_em: datetime; encerrada_em: datetime | None

class MensagemConversa(BaseModel):
    id: str; conversa_id: str; role: str; conteudo: str; criado_em: datetime

class ItemIntento(BaseModel):
    produto_id: str; codigo_externo: str; nome_produto: str; quantidade: int; preco_unitario: Decimal

class IntentoPedido(BaseModel):
    tenant_id: str; cliente_b2b_id: str | None; representante_id: str | None
    telefone_solicitante: str; itens: list[ItemIntento]
```

**Modelos orders/types.py:**
```python
class StatusPedido(StrEnum): PENDENTE = "pendente"; CONFIRMADO = "confirmado"; CANCELADO = "cancelado"

class ItemPedidoInput(BaseModel):
    produto_id: str; codigo_externo: str; nome_produto: str; quantidade: int; preco_unitario: Decimal

class ItemPedido(BaseModel):  # from_attributes=True
    id: str; pedido_id: str; produto_id: str; codigo_externo: str; nome_produto: str
    quantidade: int; preco_unitario: Decimal; subtotal: Decimal

class CriarPedidoInput(BaseModel):
    tenant_id: str; cliente_b2b_id: str | None; representante_id: str | None; itens: list[ItemPedidoInput]

class Pedido(BaseModel):  # from_attributes=True
    id: str; tenant_id: str; cliente_b2b_id: str | None; representante_id: str | None
    status: StatusPedido; total_estimado: Decimal; pdf_path: str | None; criado_em: datetime
    itens: list[ItemPedido] = []
```

**Critérios:**
- [ ] `agents/types.py` ainda importa apenas stdlib + pydantic (camada Types)
- [ ] `orders/types.py` importa apenas stdlib + pydantic (camada Types)
- [ ] `lint-imports` sem violação em src.*.types

---

### E3 — Repositórios novos

**Arquivos:**
- `output/src/agents/repo.py` — adicionar: `ClienteB2BRepo`, `RepresentanteRepo`, `ConversaRepo`
- `output/src/orders/repo.py` — criar: `OrderRepo`

**ClienteB2BRepo:**
```python
async def get_by_telefone(self, tenant_id: str, telefone: str, session) -> ClienteB2B | None
async def create(self, tenant_id: str, cliente: ClienteB2B, session) -> ClienteB2B
```

**RepresentanteRepo:**
```python
async def get_by_telefone(self, tenant_id: str, telefone: str, session) -> Representante | None
```

**ConversaRepo:**
```python
async def get_or_create_conversa(self, tenant_id: str, telefone: str, persona: Persona, session) -> Conversa
async def add_mensagem(self, conversa_id: str, role: str, conteudo: str, session) -> MensagemConversa
async def get_historico(self, conversa_id: str, limit: int, session) -> list[MensagemConversa]
async def encerrar_conversa(self, conversa_id: str, session) -> None
```

**OrderRepo:**
```python
async def criar_pedido(self, pedido: Pedido, itens: list[ItemPedido], session) -> Pedido  # retorna com id via RETURNING
async def get_pedido(self, tenant_id: str, pedido_id: str, session) -> Pedido | None  # inclui itens
async def get_pedidos_pendentes(self, tenant_id: str, session) -> list[Pedido]
async def update_pdf_path(self, tenant_id: str, pedido_id: str, pdf_path: str, session) -> None
```

**Critérios:**
- [ ] Todos os métodos públicos de repo têm `tenant_id` onde aplicável
- [ ] Nenhum repo importa service, runtime ou ui
- [ ] `lint-imports` sem violação em src.*.repo

---

### E4 — Serviços e Config

**Arquivos:**
- `output/src/orders/config.py` — criar: `OrderConfig` (pdf_storage_path via `PDF_STORAGE_PATH`, default `./pdfs`)
- `output/src/orders/service.py` — criar: `OrderService`
- `output/src/agents/config.py` — adicionar: `AgentClienteConfig`
- `output/src/agents/service.py` — reescrever `IdentityRouter.resolve()` real; adicionar `send_whatsapp_media()`

**AgentClienteConfig (agents/config.py):**
```python
class AgentClienteConfig:
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024
    max_tool_iterations: int = 5
    redis_history_ttl: int = 86400      # 24h
    redis_history_max_messages: int = 20
    pdf_storage_path: str = os.getenv("PDF_STORAGE_PATH", "./pdfs")
    system_prompt_template: str  # ver spec do AgentCliente
```

**IdentityRouter real (agents/service.py):**
```python
async def resolve(self, mensagem: Mensagem, tenant_id: str, session: AsyncSession) -> Persona:
    telefone = mensagem.de.split("@")[0]  # normaliza E.164
    if await ClienteB2BRepo().get_by_telefone(tenant_id, telefone, session): return Persona.CLIENTE_B2B
    if await RepresentanteRepo().get_by_telefone(tenant_id, telefone, session): return Persona.REPRESENTANTE
    return Persona.DESCONHECIDO
```

**send_whatsapp_media (agents/service.py):**
```python
async def send_whatsapp_media(instancia_id: str, numero: str, pdf_bytes: bytes, filename: str, caption: str = "") -> None
# POST {EVOLUTION_API_URL}/message/sendMedia/{instancia_id}
# body: {"number": numero, "mediatype": "document", "mimetype": "application/pdf",
#        "caption": caption, "media": base64(pdf_bytes), "fileName": filename}
# Erro não propaga — background task seguro
```

**OrderService (orders/service.py):**
```python
async def criar_pedido_from_intent(self, tenant_id: str, cliente_b2b_id: str | None,
    representante_id: str | None, itens: list[ItemPedidoInput]) -> Pedido
    # calcula total_estimado = sum(qtd * preco) em Python; persiste via OrderRepo
async def update_pdf_path(self, tenant_id: str, pedido_id: str, pdf_path: str) -> None
async def get_pedidos_pendentes(self, tenant_id: str) -> list[Pedido]
```

**Critérios:**
- [ ] IdentityRouter usa `ClienteB2BRepo` e `RepresentanteRepo` (não stubs)
- [ ] `send_whatsapp_media` usa base64 + Evolution API endpoint correto
- [ ] `OrderService` calcula `total_estimado` em Python
- [ ] Nenhum service importa runtime ou ui
- [ ] OTel span em `IdentityRouter.resolve` com `tenant_id`

---

### E5 — Runtime: PDFGenerator

**Arquivo:** `output/src/orders/runtime/__init__.py` + `output/src/orders/runtime/pdf_generator.py`

**Dependências:** `fpdf2>=2.7.0` (adicionar em pyproject.toml)

**Interface:**
```python
class PDFGenerator:
    def gerar_pdf_pedido(self, pedido: Pedido, tenant: Tenant) -> bytes: ...
```

**Layout PDF (A4 portrait, fpdf2):**
- Header: nome do tenant em fundo azul escuro (#003087), branco, bold
- Bloco: ID curto `PED-{pedido.id[:8]}` + data/hora
- Bloco: dados do cliente B2B (se disponível)
- Tabela itens: Código | Produto | Qtd | Preço Unit. | Subtotal
  - linhas alternadas branco/#F5F5F5
  - valores em `R$ {valor:,.2f}` convertido para formato BR (`1.234,56`)
- Total alinhado à direita
- Rodapé: timestamp + instrução ao gestor

**Nota:** `bytes(pdf.output())` — fpdf2 2.x retorna bytearray; encapsular em `bytes()`.

**Imports permitidos:** apenas `orders/types`, `tenants/types`, stdlib, fpdf2

**Critérios:**
- [ ] Retorna `bytes` (não bytearray)
- [ ] Não importa nada de `agents/` ou `catalog/`
- [ ] PDF > 1024 bytes com dados de fixture
- [ ] Nome do tenant aparece no conteúdo do PDF
- [ ] Total aparece formatado em reais

---

### E6 — Runtime: AgentCliente (Claude SDK)

**Arquivo:** `output/src/agents/runtime/agent_cliente.py` — **REESCREVER COMPLETAMENTE**

**Construtor (injeção de dependências):**
```python
class AgentCliente:
    def __init__(self,
        catalog_service: CatalogService,
        order_service: OrderService,
        conversa_repo: ConversaRepo,
        config: AgentClienteConfig,
    ) -> None: ...

    async def responder(self, mensagem: Mensagem, tenant: Tenant,
                        instancia: WhatsappInstancia, session: AsyncSession,
                        redis: Redis) -> None: ...
```

**System prompt:**
```
Você é um assistente de vendas B2B da {tenant_nome}.
Seu objetivo é ajudar clientes a encontrar produtos no catálogo e registrar pedidos.
Seja objetivo e profissional. Fale sempre em português.
Ao buscar produtos, use a ferramenta buscar_produtos com a descrição do que o cliente quer.
Ao confirmar um pedido, liste todos os itens com quantidades e preços e use confirmar_pedido.
Nunca invente preços — use apenas os retornados pela busca.
```

**Ferramentas expostas ao modelo:**

`buscar_produtos`:
- input: `query: str`, `limit: int = 5`
- executa: `catalog_service.buscar_semantico(tenant_id, query, limit)`
- retorno: JSON com `[{codigo_externo, nome, marca, categoria, preco_padrao}]`

`confirmar_pedido`:
- input: `itens: list[{codigo_externo, nome_produto, quantidade, preco_unitario}]`, `observacao?: str`
- executa: `order_service.criar_pedido_from_intent()` → `PDFGenerator().gerar_pdf_pedido()` → `send_whatsapp_media()`
- notifica: `tenant.whatsapp_number` (e `representante.telefone` se representante_id presente)

**Loop de conversa (imperativo, não recursivo):**
```
1. Carrega histórico Redis: key conv:{tenant_id}:{telefone}, TTL 24h, max 20 msgs
2. Appenda mensagem do usuário
3. anthropic.messages.create(model, system, messages, tools, max_tokens)
4. Se stop_reason == "tool_use":
   a. Executa ferramenta solicitada
   b. Appenda tool_use block + tool_result block
   c. Loop (máx 5 iterações — impede runaway)
5. Se stop_reason == "end_turn":
   a. Extrai TextBlock (verificar que existe antes de extrair)
   b. ConversaRepo.add_mensagem (user + assistant)
   c. Atualiza Redis com histórico atualizado
   d. send_whatsapp_message() com resposta textual
```

**Critérios:**
- [ ] `AgentCliente` recebe deps no construtor (testável sem monkey-patching)
- [ ] Loop limitado a `max_tool_iterations` (default 5)
- [ ] `stop_reason == "tool_use"` sem TextBlock não provoca KeyError
- [ ] Histórico Redis carregado no início de cada turno
- [ ] Mensagens persistidas no DB após cada turno
- [ ] `send_whatsapp_media` chamado ao confirmar pedido
- [ ] OTel span `agent_cliente_responder` com tenant_id
- [ ] Nenhum `print()` — structlog apenas

---

### E7 — Atualização de agents/ui.py e main.py

**agents/ui.py — atualizar `_process_message`:**
```python
# Construir AgentCliente com dependências injetadas
from src.catalog.service import CatalogService
from src.catalog.repo import CatalogRepo
from src.orders.service import OrderService
from src.orders.repo import OrderRepo
from src.agents.config import AgentClienteConfig
from src.agents.repo import ConversaRepo
from src.providers.db import get_redis

catalog_service = CatalogService(CatalogRepo(), factory)
order_service = OrderService(OrderRepo(), factory)
conversa_repo = ConversaRepo()
config = AgentClienteConfig()
redis = get_redis()

agent = AgentCliente(catalog_service, order_service, conversa_repo, config)
await agent.responder(mensagem, tenant, instancia, session, redis)
```

**main.py — adicionar no lifespan:**
```python
from src.orders.config import OrderConfig
pdf_dir = Path(OrderConfig().pdf_storage_path)
pdf_dir.mkdir(parents=True, exist_ok=True)
```

**main.py — montar /pdfs:**
```python
pdfs_dir = Path(OrderConfig().pdf_storage_path)
app.mount("/pdfs", StaticFiles(directory=str(pdfs_dir)), name="pdfs")
```

**pyproject.toml — adicionar dependência:**
```toml
"fpdf2>=2.7.0",
```

---

### E8 — Testes unitários

**Arquivos:**
- `output/src/tests/unit/agents/test_identity_router.py` — **REESCREVER** (5 casos)
- `output/src/tests/unit/agents/test_agent_cliente.py` — **REESCREVER** (7 casos)
- `output/src/tests/unit/orders/__init__.py` — criar vazio
- `output/src/tests/unit/orders/test_types.py` — criar (3 casos)
- `output/src/tests/unit/orders/test_repo.py` — criar (4 casos)
- `output/src/tests/unit/orders/test_service.py` — criar (3 casos)
- `output/src/tests/unit/orders/test_pdf_generator.py` — criar (4 casos)

**test_identity_router.py (5 casos):**
1. telefone em `clientes_b2b` → CLIENTE_B2B
2. telefone só em `representantes` → REPRESENTANTE
3. telefone em nenhum → DESCONHECIDO
4. número `5519999@s.whatsapp.net` → repo chamado com `5519999`
5. telefone em ambos → CLIENTE_B2B tem prioridade

**test_agent_cliente.py (7 casos):**
1. `anthropic.messages.create` chamado com model correto
2. `stop_reason == "tool_use"` com `buscar_produtos` → `CatalogService.buscar_semantico` chamado
3. `stop_reason == "tool_use"` com `confirmar_pedido` → `OrderService.criar_pedido_from_intent` chamado
4. `stop_reason == "end_turn"` → `send_whatsapp_message` chamado
5. Mock sempre retorna tool_use → após 5 iterações, encerra sem loop infinito
6. Redis retorna histórico → histórico incluído nas messages do Claude
7. `ConversaRepo.add_mensagem` chamado após turno encerrado

**test_pdf_generator.py (4 casos):**
1. `gerar_pdf_pedido` retorna `bytes`
2. Retorno > 1024 bytes
3. Conteúdo contém nome do tenant
4. Conteúdo contém total formatado

---

## Fora do escopo

- AgentRep com Claude SDK (permanece template; Sprint 3)
- Painel de pedidos REST (Sprint 4)
- Integração ERP para confirmação de pedido
- Preços diferenciados por cliente
- Refresh token JWT
- Rate limiting
- Segundo tenant real

---

## Riscos

| Risco | Probabilidade | Mitigação |
|-------|--------------|-----------|
| `fpdf2.output()` retorna bytearray (não bytes) | Alta | Sempre encapsular: `bytes(pdf.output())` |
| `subtotal` como coluna gerada — gotcha SQLAlchemy | Alta | Calcular em Python, salvar como NUMERIC regular |
| AgentCliente importa de orders/ — violação cross-domain? | Baixa | import-linter não proíbe cross-domain em runtime; só proíbe camadas erradas |
| `stop_reason == "tool_use"` sem TextBlock → KeyError | Média | Verificar existência de TextBlock antes de extrair |
| Redis key sem normalização de telefone → colisão | Baixa | `_normalize_phone` privado em ConversaRepo strip `@s.whatsapp.net` |

---

## Handoff para Sprint 3

Sprint 3 (AgentRep) encontrará:
- **IdentityRouter real** funcional → reps identificados automaticamente
- **ConversaRepo + Redis** operacional → memória reutilizável por AgentRep
- **OrderService** operacional → AgentRep usa o mesmo serviço para pedidos em nome de clientes
- **PDFGenerator** operacional → AgentRep usa o mesmo gerador
- **clientes_b2b + representantes** tabelas populadas → lookup funcional
