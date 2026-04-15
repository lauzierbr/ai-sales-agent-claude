# Homologação Sprint 2 — Agente Cliente Completo

**Status:** APROVADO ✅  
**Data:** 2026-04-15  
**Executado por:** Lauzier  
**QA Evaluator:** APROVADO (`artifacts/qa_sprint_2.md`)

## Resultado Final

| Cenário | Resultado |
|---------|-----------|
| C1 — Saudação e identidade | ✅ Bot responde com persona JMB |
| C2 — Busca semântica ("tem shampoo?") | ✅ 5 resultados relevantes |
| C3 — Busca por código exato | ✅ Lookup direto por `codigo_externo` |
| C4 — Confirmar pedido via WhatsApp | ✅ Pedido `a0f0df8a` criado com PDF |
| C5 — Pedido persistido no DB | ✅ `itens_pedido` com código, qtd, preço |
| C6 — Conversa persistida | ✅ 6 mensagens em `mensagens_conversa` |
| C7 — `print()` ausente | ✅ Zero ocorrências |
| C8 — Logs estruturados | ✅ structlog com `tenant_id`, hash LGPD |

**Bugs corrigidos durante homologação:**
- asyncpg + pgvector ORDER BY silencioso → workaround Python sort
- `session.commit()` ausente → pedido/conversa não persistia
- `fromMe=True` causava loop infinito de resposta
- Webhook signature: Evolution envia token simples (não HMAC)
- `distancia_maxima` ajustado de 0.4 → 0.75
- FK `itens_pedido.produto_id` (TEXT vs UUID) removida da migration

---

## Pré-condições

Execute antes de iniciar os cenários:

```bash
# 1. Deploy do código Sprint 2
./scripts/deploy.sh staging

# 2. Seed de dados reais
ssh macmini-lablz "
  cd ~/ai-sales-agent-claude/output
  export PYTHONPATH=.
  /usr/local/Cellar/infisical/0.43.72/bin/infisical run --env=staging -- \
    /Users/dev/ai-sales-agent-claude/.venv/bin/python \
    ../scripts/seed_homologacao_sprint2.py
"

# 3. Health check
curl http://100.113.28.85:8000/health
```

**Checklist pré-condições:**
- [ ] `deploy.sh staging` concluído sem erros
- [ ] Migrations 0007–0012 aplicadas (`alembic current` = head)
- [ ] Seed executado: José cadastrado em `clientes_b2b`
- [ ] Health check retorna `{"status": "ok", "version": "0.3.0"}`
- [ ] Logs sem erros críticos: `ssh macmini-lablz 'tail -20 ~/ai-sales-agent-claude/logs/app.log'`

---

## Configuração dos números

| Papel | Número | E.164 |
|-------|--------|-------|
| Bot JMB (envia como) | (19) 99146-3559 | `5519991463559` |
| Você testa enviando de | (19) 99206-6177 | `5519992066177` |

> Envie as mensagens **do número (19) 99206-6177** (José LZ Muzel)  
> **para o número (19) 99146-3559** (Bot JMB).

---

## Cenários de teste

### C1 — Saudação e identificação de persona
**Ação:** Envie "Olá" do número de José para o bot  
**Esperado:**  
- Agente responde (não silêncio)  
- Tom profissional de assistente de vendas JMB  
- Não responde com template fixo do Sprint 1 ("Sou o assistente da JMB Distribuidora. Como posso ajudar?")  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

### C2 — Busca de produto por texto
**Ação:** Envie "Tem shampoo Natura?"  
**Esperado:**  
- Agente usa ferramenta `buscar_produtos` internamente  
- Responde com produtos encontrados no catálogo (nome, código, preço)  
- Se não encontrar: informa educadamente  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

### C3 — Busca por categoria
**Ação:** Envie "Quero ver condicionadores"  
**Esperado:**  
- Retorna lista de condicionadores do catálogo JMB  
- Inclui preço unitário e código  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

### C4 — Fluxo de pedido completo
**Ação:** Após C2 ou C3, envie "Quero 10 unidades do [produto encontrado]"  
Depois confirme: "Sim, pode confirmar o pedido"  
**Esperado:**  
1. Agente usa `confirmar_pedido`  
2. Responde que o pedido foi registrado (ex: "Pedido PED-XXXXXXXX registrado!")  
3. **Gestor recebe PDF no WhatsApp** (número configurado no Infisical como `GESTOR_WHATSAPP`)  
4. PDF contém: nome do tenant, itens, total em R$  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

### C5 — Verificar pedido no banco
**Ação:** Após C4, consultar diretamente no banco:

```bash
ssh macmini-lablz "
  docker exec ai_sales_postgres psql -U aisales -d aisales -c \
  \"SELECT id, status, total_estimado, criado_em FROM pedidos WHERE tenant_id='jmb' ORDER BY criado_em DESC LIMIT 5;\"
"
```

**Esperado:**  
- Pedido aparece com `status = pendente`  
- `total_estimado` correto  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

### C6 — Conversa persiste no banco
**Ação:** Consultar conversas e mensagens:

```bash
ssh macmini-lablz "
  docker exec ai_sales_postgres psql -U aisales -d aisales -c \
  \"SELECT id, telefone, persona, iniciada_em FROM conversas WHERE tenant_id='jmb' ORDER BY iniciada_em DESC LIMIT 3;\"
"
```

**Esperado:**  
- Conversa com `telefone=5519992066177` e `persona=cliente_b2b`  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

### C7 — Número desconhecido é rejeitado silenciosamente
**Ação:** Envie uma mensagem de um **outro número** (não cadastrado em `clientes_b2b` nem `representantes`)  
**Esperado:**  
- Agente responde com mensagem de "desconhecido" (template genérico de boas-vindas)  
- NÃO tenta criar pedido, NÃO entra no loop Claude SDK  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

### C8 — Logs e observabilidade
**Ação:** Verifique os logs durante os testes:

```bash
ssh macmini-lablz 'tail -50 ~/ai-sales-agent-claude/logs/app.log'
```

**Esperado:**  
- Logs estruturados (JSON/structlog) sem `print()`  
- Campos: `tenant_id`, `persona`, `from_number_hash`  
- Sem stack traces de erro  

**Resultado:** ⬜ OK / ❌ BUG: ___

---

## Checklist de qualidade pós-testes

- [ ] Nenhum crash de servidor durante os cenários
- [ ] Tempo de resposta aceitável (< 30s por mensagem, Claude + rede)
- [ ] PDF gerado é legível e contém dados corretos
- [ ] Banco de dados consistente (pedidos, conversas, mensagens)

---

## Resultado final

**Veredicto:** PENDENTE

**Bugs encontrados:**
```
C1: 
C2: 
C3: 
C4: 
C5: 
C6: 
C7: 
C8: 
```

**Observações:**


**Próximo passo:**
- [ ] APROVADO → mover este arquivo para `completed/`, iniciar Sprint 3
- [ ] REPROVADO → bugs críticos viram hotfixes antes de Sprint 3

---

## Comandos úteis durante a homologação

```bash
# Logs em tempo real
ssh macmini-lablz 'tail -f ~/ai-sales-agent-claude/logs/app.log'

# Verificar pedidos criados
ssh macmini-lablz "docker exec ai_sales_postgres psql -U aisales -d aisales \
  -c \"SELECT id, status, total_estimado FROM pedidos WHERE tenant_id='jmb';\""

# Verificar conversas
ssh macmini-lablz "docker exec ai_sales_postgres psql -U aisales -d aisales \
  -c \"SELECT telefone, persona, iniciada_em FROM conversas WHERE tenant_id='jmb' ORDER BY iniciada_em DESC;\""

# Verificar mensagens da última conversa
ssh macmini-lablz "docker exec ai_sales_postgres psql -U aisales -d aisales \
  -c \"SELECT role, LEFT(conteudo, 80), criado_em FROM mensagens_conversa ORDER BY criado_em DESC LIMIT 20;\""

# Swagger UI
open http://100.113.28.85:8000/docs

# Grafana (traces OTel)
open http://100.113.28.85:3001
```
