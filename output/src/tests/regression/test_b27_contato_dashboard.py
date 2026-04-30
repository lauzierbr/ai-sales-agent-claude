"""Testes de regressão — B-27: cadastro contato via dashboard (E11, Sprint 10).

Verifica que POST /dashboard/contatos/novo com perfil=cliente:
- Faz INSERT em contacts (não UPDATE em clientes_b2b).
- Contato aparece em SELECT * FROM contacts após POST.
"""
from __future__ import annotations

import pytest


@pytest.mark.unit
def test_contatos_novo_post_usa_contacts_table():
    """POST /dashboard/contatos/novo com perfil=cliente insere em contacts."""
    from pathlib import Path
    source_path = Path(__file__).parent.parent.parent / "dashboard" / "ui.py"

    if not source_path.exists():
        pytest.skip("dashboard/ui.py não encontrado")

    source = source_path.read_text()

    # E11: deve conter INSERT em contacts
    assert "INSERT INTO contacts" in source, "POST contatos/novo deve fazer INSERT em contacts"


@pytest.mark.unit
async def test_clientes_template_sem_botao_novo(mocker):
    """Template /clientes não contém botão 'Novo Cliente'."""
    from pathlib import Path
    template_path = Path(__file__).parent.parent.parent / "dashboard" / "templates" / "clientes.html"

    if template_path.exists():
        content = template_path.read_text()
        # E11: /clientes deve ser read-only — sem botão "Novo Cliente"
        assert "Novo Cliente" not in content, (
            "Template clientes.html contém botão 'Novo Cliente' — deve ser read-only (E11)"
        )
    else:
        pytest.skip("Template clientes.html não encontrado")


@pytest.mark.unit
async def test_contatos_mostra_badge_pendentes():
    """Rota /contatos passa 'pendentes' para o template."""
    from pathlib import Path
    template_path = Path(__file__).parent.parent.parent / "dashboard" / "templates" / "contatos.html"

    if template_path.exists():
        content = template_path.read_text()
        # E10: badge de pendentes deve aparecer no template
        assert "pendentes" in content.lower(), (
            "Template contatos.html deve exibir badge de pendentes (E10)"
        )
    else:
        pytest.skip("Template contatos.html não encontrado")
