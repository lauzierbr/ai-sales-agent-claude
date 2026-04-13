-- Inicialização do banco ai_sales_agent
-- Executado automaticamente pelo container PostgreSQL na primeira inicialização

-- Habilitar extensão pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Habilitar extensão para UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Schema base (aplicação cria schemas por tenant dinamicamente)
-- tenant_{id} schemas são criados via migrations da aplicação

-- Tabela de controle de tenants (schema público)
CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug        TEXT UNIQUE NOT NULL,  -- ex: "jmb", "distribuidora-x"
    nome        TEXT NOT NULL,
    ativo       BOOLEAN DEFAULT TRUE,
    criado_em   TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Tenant piloto JMB (usado em desenvolvimento)
INSERT INTO tenants (slug, nome) VALUES ('jmb', 'JMB Distribuidora')
ON CONFLICT (slug) DO NOTHING;

-- Log de criação
DO $$
BEGIN
    RAISE NOTICE 'Banco ai_sales_agent inicializado com pgvector e tenant JMB';
END $$;
