# Política de Segurança

## Reportando uma vulnerabilidade

Se você encontrou uma vulnerabilidade de segurança neste repositório,
**não abra uma issue pública**. Reporte de forma privada usando o
recurso *Private vulnerability reporting* do GitHub, na aba
[Security](../../security/advisories/new) deste repositório.

Se preferir outro canal, envie um e-mail para a equipe de tecnologia da
SEEG descrevendo:

- o componente afetado (ex.: `apps/api`, `apps/facial-svc`, `apps/web`);
- passos para reproduzir, incluindo requisição/payload quando aplicável;
- impacto esperado (o que um atacante conseguiria fazer);
- se possível, uma sugestão de correção.

## O que esperar

- Confirmação de recebimento em até 5 dias úteis.
- Este é um sistema de ponto eletrônico multi-tenant que trata dados
  biométricos e trabalhistas (LGPD art. 5º, II — dado pessoal
  sensível). Vulnerabilidades que afetem isolamento entre empresas
  (RLS), autenticação, biometria ou integridade de marcação são
  tratadas com prioridade máxima.
- Pedimos que você não explore a vulnerabilidade além do necessário
  para demonstrá-la, e que não acesse dados de terceiros reais.

## Escopo

Este repositório é código-fonte publicado para transparência e
consulta (veja [LICENSE](LICENSE)) — não há programa de recompensa
(bug bounty) associado.
