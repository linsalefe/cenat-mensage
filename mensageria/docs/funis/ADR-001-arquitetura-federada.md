# ADR-001 — Arquitetura federada para o Hub de Funis

- **Status:** aceita (Etapa 0A, 03/11/2026)
- **Escopo:** onde vive cada responsabilidade dos funis de vendas do CENAT

## Contexto

O CENAT opera hoje três sistemas que tocam o mesmo lead:

| Sistema | Onde | Papel atual |
|---|---|---|
| **Mensage** (este repo) | `cenat.whatsflow.cloud` | WhatsApp/Instagram, contatos, CRM, disparos, chatbot e agente de IA |
| **Dash** | `dash.cenatdata.online` | BI e mídia paga |
| **Cenat Hub** | `hub.cenatdata.online` | Operação comercial da Pós no Exact |

Os funis (Low ticket, Curso livre, Comunidade, Congressos, Pós com seminário pago
como front end) atravessam os três. Falta um lugar que saiba **quem é a pessoa e em
que ponto da jornada ela está**, e que dispare as automações certas.

## Opções

> A decisão (B) veio pronta da definição do projeto. As descrições de A e C abaixo
> são a reconstrução das alternativas óbvias, para registrar o porquê; valide
> contra o plano original.

- **A — Monólito no Mensage.** Trazer BI e a operação da Pós para dentro do
  Mensage. Um banco só, mas reescreve dois sistemas que funcionam e põe carga de
  BI no mesmo Postgres/processo que atende o WhatsApp de produção (`--workers 1`).
- **B — Federada (escolhida).** Cada sistema mantém seu domínio; o Mensage passa
  a ser o dono da **pessoa + jornada + automações**. Os outros continuam donos de
  BI/mídia (Dash) e da operação comercial da Pós (Cenat Hub).
- **C — Novo hub central.** Um quarto sistema (ou data warehouse) que agrega os
  três. Mais limpo no papel, mas cria mais uma peça para operar e não resolve as
  automações, que precisam estar perto do canal de mensagem.

## Decisão

**B — federada.**

| Sistema | É dono de |
|---|---|
| Mensage | pessoa, jornada no funil, automações |
| Dash | BI e mídia |
| Cenat Hub | operação comercial da Pós no Exact |

**Chave comum entre os sistemas:** `cn_aid` + telefone normalizado + e-mail.

## Consequências

- O Mensage ganha o modelo de funil (Etapa 0B: `products`, `funnels`,
  `funnel_stages`, `funnel_actions`, `funnel_events`, `contact_touchpoints`,
  `contacts.email`/`cpf`).
- Toda integração precisa casar a pessoa pela chave comum — telefone tem que ser
  normalizado do mesmo jeito nos três lados (ver `app/agent/phone.py` para a
  tolerância ao 9º dígito já usada aqui).
- **Nenhuma integração na Etapa 0A.** Elas entram em etapas próprias.
- A ponte Mensage→Customer (`relay/`) já existe e historicamente devolve 404 —
  não serve de modelo de confiabilidade para as integrações novas.

## Quando reavaliar

- Se a sincronização entre os três sistemas virar a maior fonte de bug/retrabalho.
- Se o casamento pela chave comum falhar com frequência (pessoa duplicada entre
  sistemas).
- Se um dos sistemas for descontinuado ou reescrito.
