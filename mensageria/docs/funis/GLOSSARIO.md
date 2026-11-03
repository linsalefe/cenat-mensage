# Glossário — Hub de Funis

Termos ainda sem definição fechada estão marcados **(pendente)**.

## Funil

- **Funil** — caminho de uma pessoa de desconhecida a cliente (e recorrente) para
  um produto ou família de produtos. Os do CENAT: Low ticket, Curso livre,
  Comunidade, Congressos, Pós (com seminário pago como front end).
- **Etapa** — fase do funil. Quatro, nesta ordem:
  - **Aquisição** — a pessoa chega (anúncio, orgânico, indicação) e vira lead.
  - **Conversão** — primeira compra.
  - **Monetização** — aumenta o valor da compra (upsell, order bump).
  - **Expansão** — recompra, outro produto, outro funil.
- **Ação de funil** — algo que o sistema faz numa etapa: mensagem, template,
  tag, mudança de estágio, tarefa para humano.

## Pessoa

- **Lead** — pessoa com algum contato identificado (telefone ou e-mail) que
  demonstrou interesse.
- **MQL** — *Marketing Qualified Lead*. **(pendente)** — o critério de
  qualificação do CENAT ainda não foi definido.

## Atribuição

- **`cn_aid`** — identificador da pessoa compartilhado entre os sistemas do
  CENAT; junto com telefone normalizado e e-mail, é a chave comum da
  [ADR-001](ADR-001-arquitetura-federada.md). **(pendente)** — formato e origem
  não definidos; não existe no código do Mensage em 03/11/2026.
- **UTM** — parâmetros `utm_source`, `utm_medium`, `utm_campaign`,
  `utm_content`, `utm_term` na URL de entrada; dizem de onde a pessoa veio.
- **Primeiro toque / último toque** — o primeiro e o último ponto de contato
  registrados antes da conversão. Modelos de atribuição diferentes creditam um
  ou outro.

## Oferta

- **Front end** — o produto de entrada do funil, barato ou de baixo atrito (na
  Pós, o seminário pago).
- **Upsell** — oferta de um produto maior/melhor depois (ou no lugar) da compra.
- **Order bump** — item adicional oferecido no próprio checkout, com um clique.
- **Cashback** — crédito devolvido ao cliente para usar numa próxima compra.

## Operação

- **Canal** — número/conta de mensagem cadastrado no Mensage
  (`mensageria.channels`): WhatsApp oficial (Meta), WhatsApp Evolution ou
  Instagram.
- **Cota diária** — limite de envios por canal por dia: o tier de mensagens da
  Meta por número e/ou um teto nosso para proteger a qualidade do número.
  **(pendente)** — qual dos dois o plano adota.
