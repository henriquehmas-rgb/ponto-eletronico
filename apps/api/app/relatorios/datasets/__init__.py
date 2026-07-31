"""Pacote de datasets do catálogo de relatórios (F11).

Cada módulo registra suas funções de consulta em `app.relatorios.catalogo`
na importação (`registrar_dataset`). Este pacote não define nenhuma função
própria -- só agrupa `operacionais.py` (A2), `gerenciais.py` (A3) e
`espelho_oficial.py` (A4).

Os três `import` abaixo são de EFEITO COLATERAL (nenhum símbolo é usado
diretamente aqui): é o que garante que os `registrar_dataset(...)` de cada
módulo já rodaram antes da primeira requisição, bastando importar este
pacote uma vez em algum ponto do boot da aplicação. Quem importa este
pacote é `app/routers/relatorios.py` (A1, T3) -- ver o comentário lá; sem
essa importação em algum lugar, `app.relatorios.catalogo.obter_dataset`
nunca encontraria as 24 funções reais, mesmo com as 24 linhas de
`relatorio_definicoes` já semeadas (achado real de integração entre os
quatro agentes desta fase, corrigido durante o desenvolvimento de T1-T3)."""

from __future__ import annotations

from app.relatorios.datasets import espelho_oficial as _espelho_oficial  # noqa: F401
from app.relatorios.datasets import gerenciais as _gerenciais  # noqa: F401
from app.relatorios.datasets import operacionais as _operacionais  # noqa: F401
