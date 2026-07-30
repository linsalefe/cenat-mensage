# BASE_CONHECIMENTO_POS.md — Pós-Graduações CENAT (kind: "pos")

> Fonte de dados para `agent_products` (kind="pos"). O agente INFORMA e ENCAMINHA
> ao comercial — NÃO vende, não gera link de pagamento, não fecha condição.
> Promoções têm validade; o agente só enxerga promo vigente na data da conversa.

**Coleta:** `scripts/extrair_pos.py` (13/13 landings, HTTP 200 em 30/07/2026).
Saídas: `scripts/data/pos_extraido.json` (fonte do seed) e
`scripts/data/pos_extraido.md` (relatório cru com os avisos por campo).
Todo ⚠️ abaixo veio de um aviso automático da extração — nenhum valor foi inferido
ou calculado por conta própria.

## Regras do agente para pós (vão para o prompt)

- Papel: tirar dúvidas (curso, modalidade, carga horária, início, investimento e
  promoção vigente), qualificar (nome, curso de interesse, formação, melhor
  horário) e acionar `encaminhar_comercial_pos` com o resumo na nota do contato.
- Inscrição na pós é por PROCESSO SELETIVO: pré-aplicação no site → agendamento
  → entrevista com a equipe. O agente explica esse caminho e/ou encaminha
  direto ao comercial. Nunca promete vaga nem condição fora da base.
- Requisito MEC: graduação concluída (bacharelado, licenciatura ou tecnólogo).
  Não é possível iniciar antes de concluir a graduação.
- Benefícios padrão (confirmar por curso): sem TCC (seminários avaliativos por
  módulo), aulas ao vivo gravadas, Clube Carreira CENAT (divulgação
  profissional + 50% de desconto na 2ª pós), garantia de satisfação (cancelar
  sem multa ao fim do 1º módulo), isenção de matrícula, dedutível do IR.
- Contatos do funil de pós: processoseletivo@cenatsaudemental.com |
  WhatsApp (11) 95213-7432 (link: https://wa.me/5511952137432).
  ✅ Confirmado: os dois contatos aparecem no rodapé das 13 landings.

## Promoção vigente (atualizar todo mês!)

| campo | valor |
|---|---|
| descricao | 25% OFF no cartão por recorrência |
| valido_de | ⚠️ nenhuma página publica a data de início da promo |
| valido_ate | 2026-07-31 |
| cupom | (nenhum — desconto aplicado na página) |
| condicao | desconto já aplicado nos valores anunciados; cartão por recorrência |
| escopo | **todas as 13** — ver abaixo |

**Resposta à pergunta do escopo:** a promoção de 25% até 31/07 aparece em
**13/13 landings** — não é de algumas só. A extração confirma badge de promo em
todas, todas com o mesmo prazo (31/07) e todas com o mesmo percentual (25%).
O que varia é só a *redação* do badge (`25% OFF — CARTÃO POR RECORRÊNCIA`,
`25% DE DESCONTO ATÉ 31/07`, `25% OFF até 31/07`) — a régua de desconto é a mesma.

⚠️ **O ano do prazo não está escrito em nenhuma página** — todas dizem "até 31/07",
sem ano. Assumi 2026 (`--ano=2026`). Como hoje é 30/07/2026, a promo vence
**amanhã**: no dia 01/08 o filtro determinístico de vigência apaga a promo de todos
os 13 cursos de uma vez e o agente passa a informar só o valor cheio. Vale decidir
já se a promo vai ser renovada — e, se for, com que prazo.

---

## ⚠️ Pendências que precisam da sua decisão antes da Etapa B

### 1. Certificadora: não achei nenhuma pós certificada pela CENSUPEG
O briefing dizia "algumas são Faculdade de São Marcos, outras CENSUPEG". A
extração encontrou **Faculdade de São Marcos nas 13**, sempre com a mesma
Portaria MEC nº 1.371/2012:

| texto encontrado | cursos |
|---|---|
| `Faculdade de São Marcos — Portaria nº 1.371/2012` | 6 (sm-trabalho-t3, mulheridades, grupos-oficinas-t2, gestao-t5, psicologia-clinica-t2, alcool-drogas-t4) |
| `Faculdade São Marcos — Portaria nº 1.371/2012` | 7 (psicologia-raps, psicologia-escolar, tea, economia-solidaria, dialogo-aberto, suicidio-t3, psicologia-hospitalar) |

A diferença é só o "de" na grafia; a Portaria é idêntica, logo é a mesma
instituição. "CENSUPEG" aparece nas páginas **apenas em bio de docente**
("Professor no CENAT/CENSUPEG", "coordenadora de pós-graduação pela Censupeg") —
nunca como certificadora do curso.
**Pergunta:** semeio todas como Faculdade de São Marcos, ou existe curso com
certificação CENSUPEG que a landing não reflete?

### 2. Quatro turmas com início já no passado
`suicidio-t3` (11/06/2026), `psicologia-clinica-t2` (20/05/2026),
`alcool-drogas-t4` (23/05/2026), `psicologia-hospitalar` (27/05/2026) —
todas anteriores a hoje (30/07/2026). Ou a landing está desatualizada, ou a turma
já começou e a página segue captando.
**Pergunta:** qual a data real de início dessas 4? Enquanto não confirmar, o
seed guarda a data como está e marca `inicio_confirmado=false`, e o prompt proíbe
o agente de anunciar data de início desses 4 cursos (ele encaminha ao comercial).

### 3. Dois cursos sem valor total publicado
`gestao-t5` e `psicologia-hospitalar` anunciam **só por parcela**: "DE R$ 340,00,
POR R$ 255,00 por parcela / 20x de R$ 255,00". As outras 11 anunciam o total
("DE R$ 6.800,00, POR R$ 5.100,00 à vista").
20 × 340 = 6.800 e 20 × 255 = 5.100 — bate com as demais, **mas a página não diz
isso**, então não gravei o total. Sem sua confirmação esses 2 cursos ficam com
`preco_cheio=null` e o agente só informa a parcela.
**Pergunta:** confirmo total de R$ 6.800 / R$ 5.100 à vista para os dois?

### 4. Landing da RAPS tem conteúdo da Psicologia Escolar
Em `pospsicologianaraps.cenatsaudemental.com` o H1, os módulos e o coordenador
(Bruno Emerich) são de RAPS, mas o público-alvo, o FAQ "quem pode fazer" e o CTA
final falam de **contexto escolar**: *"Psicólogos que atuam ou pretendem atuar em
instituições educacionais... inclusão escolar, acompanhamento psicopedagógico"* —
texto idêntico ao da landing de Psicologia Escolar.
É bug de conteúdo na página, não da extração. **Não vou semear o público-alvo
desse curso** até você confirmar o texto correto (ou pedir para eu usar o
boilerplate genérico das outras).

### 5. Bônus vencido na landing de Mulheridades
A página ainda anuncia: *"Faça sua matrícula em junho e ganhe 6 supervisões em
grupo... pacote avaliado em R$ 2.100"*. Junho já passou. Não vou semear como
promo ativa. **Pergunta:** o bônus foi renovado ou saiu?

### 6. Duração divergente em Saúde Mental no Trabalho (T3)
A mesma página diz "13 meses" na seção de disciplinas e "14 meses" na de
investimento (o FAQ diz início 03/11/2026 → término dez/2027, ≈14 meses).
Mantive `13 ou 14 meses` com ⚠️. **Pergunta:** qual vale?

---

## 1. Boas Práticas em Saúde Mental nas Organizações e no Trabalho (T3)

| campo | valor |
|---|---|
| slug | `pos-sm-trabalho-t3` |
| landing | https://posmdotrabalhadort3.cenatsaudemental.com/ |
| turma | Turma 3 |
| inicio_aulas | 03/11/2026 (término previsto dez/2027, pelo FAQ) |
| carga_horaria | 390 horas · 4 módulos |
| duracao | ⚠️ 13 ou 14 meses (página divergente — ver pendência 6) |
| aulas | Terças-feiras, 19h–22h · online ao vivo (gravadas na plataforma) |
| certificacao | MEC — Faculdade de São Marcos (Portaria nº 1.371/2012); Especialista, lato sensu, validade nacional |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Profissionais graduados em psicologia, medicina, enfermagem, terapia ocupacional, serviço social e outras categorias atuantes no campo de saúde mental, na rede pública ou privada |
| perfis | Profissionais de RH e gestão de pessoas · Profissionais da clínica e da saúde do trabalhador · Lideranças, gestoras(es) e consultoras(es) |
| modulos | 1) Bases Conceituais do Cuidado em Saúde Mental, Saúde e Trabalho (72h) · 2) Saúde Mental e Trabalho (111h) · 3) Saúde Mental nas Organizações (111h) · 4) Promoção e Prevenção de Saúde Mental no Ambiente de Trabalho (96h) |
| temas_chave | NR-1, riscos psicossociais, PGR/GRO, burnout, assédio, manejo de crise e ideação suicida no trabalho, CNV, mediação de conflitos, compliance, programas de saúde mental nas empresas |
| coordenacao | Thiago Magela Ramos (enfermeiro, mestre em Saúde Coletiva/UFSJ) |
| docentes | Leonardo Duart Bastos · Fernanda Moura Miranda (UFPR) · Nazareth Malcher (UnB) |
| diferenciais | Sem TCC · garantia de satisfação (1º módulo) · isenção de matrícula · Carteira de Estudante · Clube Carreira · dedutível do IR |

## 2. Psicologia na RAPS

| campo | valor |
|---|---|
| slug | `pos-psicologia-raps` |
| landing | https://pospsicologianaraps.cenatsaudemental.com/ |
| turma | Turma Nova · Início 01/10/2026 |
| inicio_aulas | 01/10/2026 |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 13 meses |
| aulas | Quintas-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | ⚠️ **NÃO SEMEAR** — a landing traz o público-alvo da Psicologia Escolar (ver pendência 4) |
| perfis | ⚠️ idem (a página lista "Psicólogos da educação", "Equipes multiprofissionais da escola") |
| modulos | 1) Psicologia na Atenção Psicossocial: Elementos para a Prática no SUS e na Reforma Psiquiátrica (64h) · 2) Interseccionalidades, Psicologia Social e Institucional (88h) · 3) Ofertas de Cuidado e Compreensão do Sofrimento em Diferentes Públicos (112h) · 4) Clínicas da Psicologia nos Pontos da RAPS (96h) |
| coordenacao | Bruno Emerich |
| docentes | Silvio Yasui · Carlos Alberto Gama · Antônio Euzébios Filho · Breno de Oliveira Ferreira · Daniele de Andrade Ferrazza · Tadeu de Paula Souza |
| diferenciais | Sem TCC tradicional · garantia de satisfação · isenção de matrícula (na pré-aplicação) · Carteira de Estudante · Clube Carreira · dedutível do IR |

## 3. Psicologia Escolar

| campo | valor |
|---|---|
| slug | `pos-psicologia-escolar` |
| landing | https://pospsicologiaescolar.cenatsaudemental.com/ |
| turma | Turma Nova |
| inicio_aulas | 03/09/2026 (⚠️ badge do hero escreve "03/09/26", ano com 2 dígitos; a seção de investimento confirma 2026) |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 13 meses |
| aulas | Quintas-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Psicólogos que atuam ou pretendem atuar em instituições educacionais, com foco em desenvolvimento humano, processos de aprendizagem, inclusão escolar, saúde mental e acompanhamento psicopedagógico |
| perfis | Psicólogos da educação · Profissionais da inclusão escolar · Equipes multiprofissionais da escola |
| modulos | 1) Fundamentos da Psicologia Escolar e Desenvolvimento Humano (90h) · 2) Saúde Mental e Inclusão no Contexto Escolar (90h) · 3) Intervenções e Atuação do Psicólogo Escolar (90h) · 4) Metodologias Ativas e Inovação Educacional (90h) |
| coordenacao | Rúbia Tatiana S. de Souza Frederico |
| docentes | Marina Corbetta Benedet · Daniel Magalhães Goulart · Aline Barcellos Lopes Plácido · Ludimar Paulo Pereira · Tiago Duarte Cardoso da Silva · Luana Aparecida Couto |
| diferenciais | Sem TCC tradicional · garantia de satisfação · isenção de matrícula (na pré-aplicação) · Carteira de Estudante · Clube Carreira · dedutível do IR |
| obs | Turma com mínimo de 20 e máximo de 70 vagas |

## 4. Saúde Mental e Mulheridades

| campo | valor |
|---|---|
| slug | `pos-mulheridades` |
| landing | https://posmulheridades.cenatsaudemental.com/ |
| turma | Turma Nova |
| inicio_aulas | 08/08/2026 |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 14 meses |
| aulas | Sábados, 09h–12h · online ao vivo |
| certificacao | MEC — Faculdade de São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Profissionais e gestoras(es) com graduação que atuem no campo da saúde, saúde mental, atenção básica e atenção psicossocial, além de profissionais com graduação interessados na área |
| perfis | Profissionais da clínica em saúde mental · Profissionais da rede pública e da atenção psicossocial · Gestoras(es), pesquisadoras e profissionais do campo |
| modulos | 1) Mulheridades, Estado e Sociedade · 2) Experiências Interseccionais nas Mulheridades · 3) Instituições, Políticas e Práticas em Saúde Mental · 4) Experiências e Boas Práticas com Mulheres em Saúde Mental (⚠️ a página não publica a carga de cada módulo) |
| coordenacao | Melissa Pereira |
| docentes | Ana Terra de Leon · Rachel Gouveia Passos · Vanessa Crumial Herdy de Andrade · Arlete Inácio dos Santos · Nicola de Campos Worcman · Marisa Antunes Santiago · Adriana Soares Sá |
| diferenciais | Sem TCC · garantia de satisfação · isenção de matrícula · Carteira de Estudante · Clube Carreira · dedutível do IR |
| bonus | ⚠️ **VENCIDO, não semear** — "matrícula em junho → 6 supervisões em grupo, pacote de R$ 2.100" (ver pendência 5) |

## 5. Grupos e Oficinas em Saúde Mental (T2)

| campo | valor |
|---|---|
| slug | `pos-grupos-oficinas-t2` |
| landing | https://posgruposeoficinast2.cenatsaudemental.com/ |
| turma | Turma 2 |
| inicio_aulas | 20/10/2026 |
| carga_horaria | 360 horas · **3 eixos** (único com 3 módulos) |
| duracao | 14 meses ("aproximadamente", pelo FAQ) |
| aulas | Terças-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade de São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Profissionais e gestoras(es) com graduação que atuem no campo da saúde, saúde mental, atenção básica e atenção psicossocial, além de profissionais com graduação interessados na área |
| perfis | Trabalhadores da RAPS e do SUS · Profissionais da clínica e da saúde mental · Gestores, pesquisadores e educadores |
| modulos | 1) Fundamentos da Reforma Psiquiátrica e Conceitos de Grupos e Oficinas · 2) Práticas de Grupos e Oficinas em Saúde Mental · 3) Reflexões Sobre a Prática e Atuação Profissional (⚠️ sem carga por módulo na página) |
| coordenacao | Priscilla Cordeiro |
| docentes | Melissa Ribeiro Teixeira · Dione Maria Menz · Bruno Cobucci · Lara Carolina Ribeiro Vilanova · Ludgleydson Araujo · Loraine Oltmann de Oliveira |
| diferenciais | Sem TCC · garantia de satisfação · isenção de matrícula · Carteira de Estudante · dedutível do IR (⚠️ Clube Carreira **não** listado nesta página) |

## 6. Transtorno do Espectro Autista (TEA)

| campo | valor |
|---|---|
| slug | `pos-tea` |
| landing | https://postea.cenatsaudemental.com/ |
| turma | Turma Nova |
| inicio_aulas | 07/10/2026 |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 14 meses |
| aulas | Quartas-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Profissionais e gestoras(es) com graduação que atuem no campo da saúde, saúde mental, atenção básica e atenção psicossocial, além de profissionais com graduação interessados na área |
| perfis | Profissionais da saúde e da atenção psicossocial · Educadores e profissionais da inclusão · Pesquisadores e gestores do campo |
| modulos | 1) Fundamentos Epistemológicos e Histórico-Críticos · 2) Diagnóstico e Promoção do Desenvolvimento · 3) Abordagens Terapêuticas e Novas Práticas · 4) Práticas Interprofissionais e Cuidado em Rede (⚠️ sem carga por módulo na página) |
| coordenacao | José Fernando Patiño Torres (doutor em Educação/UnB) |
| docentes | Daniel Goulart · Thiago Magela Ramos · Ricardo Lugon · Marcelo Kimati · Ana Muhlethaler · Maristela Rossato · Hanna Patrícia da Silva Bezerra |
| diferenciais | Sem TCC · garantia de satisfação · isenção de matrícula (na pré-aplicação) · Carteira de Estudante · Clube Carreira · dedutível do IR |
| ⚠️ atenção | **TEA é pós, não congresso.** É o caso de confusão mais provável no atendimento — ver persona (d) dos evals |

## 7. Gestão, Avaliação e Planejamento na Atenção Psicossocial (T5)

| campo | valor |
|---|---|
| slug | `pos-gestao-t5` |
| landing | https://posgestaot5.cenatsaudemental.com/ |
| turma | Turma 5 |
| inicio_aulas | 04/08/2026 |
| carga_horaria | 365 horas · 4 eixos |
| duracao | 13 meses |
| aulas | Terças-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade de São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | ⚠️ **total não publicado** — a página anuncia "DE R$ 340,00/parcela" (ver pendência 3) |
| investimento_promo | 20x de R$ 255,00 (a página diz "R$ 255,00 por parcela"; não há valor à vista) |
| condicao_promo | oferta válida até 31/07 · no cartão por recorrência |
| publico | Profissionais com graduação que atuem ou desejam atuar na gestão, coordenação ou planejamento de serviços de saúde mental e atenção psicossocial |
| perfis | Coordenadores e gestores de CAPS · Trabalhadores da rede psicossocial · Profissionais em transição para gestão |
| modulos | Eixo 1) Fundamentos de Planejamento e Gestão no Campo da Atenção Psicossocial · Eixo 2) Planejamento do Cuidado e Gestão da Clínica · Eixo 3) Avaliação da Clínica e dos Serviços com foco Psicossocial · Eixo 4) Gestão de Pessoas e do Trabalho em Saúde Mental (⚠️ sem carga por eixo) |
| coordenacao | Thiago Magela Ramos |
| docentes | Rachel Gouveia · Priscilla Fraga · Milene Ramalho |
| diferenciais | Sem TCC · garantia de satisfação · isenção de matrícula · Carteira de Estudante · Clube Carreira · dedutível do IR |
| ⚠️ obs | A `<title>` da página está errada ("Pós-Graduação em Saúde Mental e Mulheridades") — copy-paste no HTML. O nome correto vem do H1 e é o que usei |

## 8. Economia Solidária, Arte e Cultura na Saúde Mental

| campo | valor |
|---|---|
| slug | `pos-economia-solidaria` |
| landing | https://poseconomiasolidaria.cenatsaudemental.com/ |
| turma | Turma 1 · Início 15/08/2026 |
| inicio_aulas | 15/08/2026 |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 15 meses |
| aulas | Sábados, 09h–12h · online ao vivo |
| certificacao | MEC — Faculdade São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Profissionais e gestores graduados que atuam ou desejam atuar no campo da saúde mental, da atenção psicossocial, da cultura, do trabalho e das políticas públicas |
| perfis | Profissionais da RAPS e do SUS · Trabalhadores da arte e da cultura · Atores da economia solidária |
| modulos | 1) Intersecções entre Saúde Mental e Economia Solidária · 2) Arte, Cultura e Economia Solidária como dispositivo de cidadania · 3) Dimensão Sociocultural no Direito ao Trabalho e Economia Solidária · 4) Tecendo Projetos de Arte e Economia Solidária (⚠️ sem carga por módulo) |
| coordenacao | Kátia Barfknecht |
| docentes | Ana Luisa Aranha e Silva · Egeu Esteves · Gislei Lazzaroto · Carolina Chassot · Cristina Lopes · Amanda Schoenmaker · Patrícia Dorneles · Marília Veronese · Arthur Romanzini Lazzarotto |
| diferenciais | Sem TCC tradicional · garantia de satisfação · isenção de matrícula (na pré-aplicação) · Carteira de Estudante · Clube Carreira · dedutível do IR |

## 9. Práticas Dialógicas e Diálogo Aberto na Saúde Mental

| campo | valor |
|---|---|
| slug | `pos-dialogo-aberto` |
| landing | https://posdialogoaberto.cenatsaudemental.com/ |
| turma | Turma 1 · Início 29/08/2026 |
| inicio_aulas | 29/08/2026 |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 14 meses |
| aulas | Sábados, 09h–12h · online ao vivo |
| certificacao | MEC — Faculdade São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | **R$ 8.100,00** (o mais caro dos 13) |
| investimento_promo | **R$ 6.075,00 à vista OU 20x de R$ 303,75** |
| condicao_promo | no cartão por recorrência |
| publico | Profissionais graduados que atuam ou desejam atuar no cuidado em saúde mental e buscam desenvolver habilidades dialógicas, de escuta qualificada e de trabalho em rede |
| perfis | Profissionais da saúde mental · Equipes que trabalham com famílias · Atuação intersetorial |
| modulos | 1) Fundamentos Históricos, Teóricos e Dialógicos do Cuidado · 2) Diálogo Aberto, Rede Social e Familiar · 3) Aplicabilidade do Diálogo Aberto · 4) Práticas Dialógicas no Contexto Brasileiro (⚠️ sem carga por módulo) |
| coordenacao | Priscilla Cordeiro · Thiago Magela · Cecília Cruz Villares |
| docentes | Jaakko Seikkula · Bruno Cobucci · Marcus Vinícius · Isabel Ferreira · José Alberto Orsi · Carla Gabriela Wünsch · Cristina Márcia Caron Ruffino |
| diferenciais | Parceria CENAT + **Instituto NOOS** · Sem TCC tradicional · garantia de satisfação · isenção de matrícula (na pré-aplicação) · Clube Carreira · dedutível do IR |
| ⚠️ atenção | **Preço diferente dos outros 12.** O agente não pode reusar "R$ 255" aqui — a parcela é R$ 303,75 |

## 10. Autolesão, Comportamento Suicida e Luto (T3)

| campo | valor |
|---|---|
| slug | `pos-suicidio-t3` |
| landing | https://possuicidiot3.cenatsaudemental.com/ |
| turma | Turma 3 · Início 11/06/2026 |
| inicio_aulas | ⚠️ 11/06/2026 — **já passou** (ver pendência 2) |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 12 meses (o mais curto) |
| aulas | Quintas-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Profissionais graduados das áreas da saúde, educação e assistência social que atuam ou desejam atuar no cuidado a pessoas em situação de autolesão, risco de suicídio e luto |
| perfis | Profissionais da saúde · Educação e assistência social · Cuidado ao luto e à posvenção |
| modulos | 1) Introdução à Saúde Mental e ao Comportamento Autolesivo · 2) O Comportamento Suicida · 3) Processos de Luto e Posvenção do Suicídio · 4) Construindo Novas Abordagens para o Cuidado da Autolesão e do Suicídio (⚠️ sem carga por módulo) |
| coordenacao | Wilzacler Rosa e Silva Pinheiro |
| docentes | Dione Menz · Edimar Costa · Ludgleydson Fernandes de Araújo · Andreia Vilas Boas · Ana Vitória Salimon · Estela Ramires Lourenço · Luana Cristina Santos · Felipe Baére |
| diferenciais | Sem TCC tradicional · garantia de satisfação · isenção de matrícula (na pré-aplicação) · Carteira de Estudante · Clube Carreira · dedutível do IR |
| ⚠️ atenção | Tema sensível. Se a pessoa falar da própria dor (ideação, luto recente), o caminho é `handoff_to_human`, não venda nem direcionamento comercial |

## 11. Psicologia Clínica e Saúde Mental (T2)

| campo | valor |
|---|---|
| slug | `pos-psicologia-clinica-t2` |
| landing | https://pospsicologiaclinicat2.cenatsaudemental.com/ |
| turma | Turma 02 |
| inicio_aulas | ⚠️ 20/05/2026 — **já passou** (ver pendência 2) |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 13 meses |
| aulas | Quartas-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade de São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | no cartão por recorrência |
| publico | Psicólogos(as) e profissionais com graduação que atuem ou queiram atuar no campo da clínica, da saúde mental e da atenção psicossocial |
| perfis | Psicólogas(os) clínicas(os) · Profissionais da rede de atenção psicossocial · Profissionais interessados em novas tendências clínicas |
| modulos | 1) Fundamentos da Psicologia Clínica · 2) Intervenções em Crises e Psicoterapia de Emergência e Desastre · 3) Avanços e Tendências em Psicologia Clínica e Saúde Mental · 4) Perspectivas Diferenciadas sobre Temas da Atualidade (⚠️ sem carga por módulo) |
| coordenacao | Wilzacler Rosa |
| docentes | Silvio Yasui · Leonardo Duart · Mariana Soares de Souza · Clarissa Webster · Ludgleydson Araujo · Bruno Emerich |
| diferenciais | Sem TCC · garantia de satisfação · isenção de matrícula · Carteira de Estudante · Clube Carreira · dedutível do IR |

## 12. Cuidado a Usuários de Álcool e Outras Drogas (T4)

| campo | valor |
|---|---|
| slug | `pos-alcool-drogas-t4` |
| landing | https://poscuidadousuariosadturma4.cenatsaudemental.com/ |
| turma | Turma 4 — Vagas Limitadas |
| inicio_aulas | ⚠️ 23/05/2026 — **já passou** (ver pendência 2) |
| carga_horaria | **362 horas** · 4 módulos |
| duracao | **16 meses** (o mais longo) |
| aulas | Sábados, 09h–12h · online ao vivo |
| certificacao | MEC — Faculdade de São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | R$ 6.800,00 |
| investimento_promo | R$ 5.100,00 à vista OU 20x de R$ 255,00 |
| condicao_promo | ⚠️ a página não repete "cartão por recorrência" na seção de investimento; o badge diz só "25% OFF ATÉ 31/07" |
| publico | Profissionais de saúde, atuantes na rede pública ou privada, com diploma de graduação concluído, interessados em se qualificar no cuidado a usuários de álcool e outras drogas |
| perfis | Profissionais da rede de atenção psicossocial · Profissionais que atuam em território e redução de danos · Gestoras(es), pesquisadoras e profissionais do campo |
| modulos | 1) O Uso de Drogas e a Política de Cuidados a Usuários no País · 2) Drogas e seus Efeitos · 3) Uso de Drogas e Vulnerabilidades · 4) Abordagem a Usuários de Drogas: Da Droga ao Sujeito (⚠️ sem carga por módulo) |
| temas_chave | Reforma Psiquiátrica, RAPS, redução de danos, território, serviços substitutivos |
| coordenacao | Rodrigo Simas |
| docentes | Ana Regina Machado · Claudio Gruber Mann · Juliana Araújo · Rossana Rameh · Bruno Emerich · Debora Ortolan · Nicola Worcman |
| diferenciais | Sem TCC · garantia de satisfação · Carteira de Estudante (meia-entrada) · Clube Carreira · dedutível do IR (⚠️ isenção de matrícula **não** listada nesta página) |

## 13. Psicologia Hospitalar

| campo | valor |
|---|---|
| slug | `pos-psicologia-hospitalar` |
| landing | https://pospsicologiahospitalar.cenatsaudemental.com/ |
| turma | Turma 1 · Início 27/05/2026 |
| inicio_aulas | ⚠️ 27/05/2026 — **já passou** (ver pendência 2) |
| carga_horaria | 360 horas · 4 módulos |
| duracao | 13 meses |
| aulas | Quartas-feiras, 19h–22h · online ao vivo |
| certificacao | MEC — Faculdade São Marcos (Portaria nº 1.371/2012) |
| investimento_cheio | ⚠️ **total não publicado** — a página anuncia "DE R$ 340,00" por parcela (ver pendência 3) |
| investimento_promo | Em até 20x de R$ 255,00 (sem valor à vista na página) |
| condicao_promo | valor com desconto já aplicado via cartão por recorrência + isenção de taxa de matrícula |
| publico | Profissionais psicólogos que atuem na Psicologia Hospitalar e profissionais graduados que trabalhem indiretamente com o campo ou tenham interesse em sua atuação |
| perfis | Psicólogos que atuam em hospitais · Quem deseja ingressar na área · Profissionais de equipes multiprofissionais |
| modulos | 1) Fundamentos da Psicologia Hospitalar · 2) Avaliação e Diagnóstico Psicológico no Contexto Hospitalar · 3) Modelos de Intervenção e Práticas Clínicas · 4) Tópicos Especiais e Atuação Interdisciplinar (⚠️ sem carga por módulo) |
| temas_chave | Atuação no leito, enfermarias e UTIs, SUS, Política Nacional de Humanização, cuidados paliativos, manejo de crises, luto e fim de vida |
| coordenacao | Juliana Siquinelli Padula |
| docentes | Dra. Giselle Fatima Silva · Vanessa Ruiz Vaz Gomez · Erika de Oliveira · Leonardo Duart Bastos · Juliana Tome Garcia · Miryelle Viana · Mariana Dantas Valle |
| diferenciais | Sem TCC tradicional · garantia de satisfação · isenção de matrícula (na pré-aplicação) · Carteira de Estudante · Clube Carreira · dedutível do IR |
| obs | Vagas limitadas — apenas 50 vagas, com processo seletivo |

---

## Resumo para o guardrail de saída (preços permitidos, kind="pos")

Valores que o agente pode dizer, vindos da base (nunca calculados na conversa):

| valor | onde aparece |
|---|---|
| R$ 6.800,00 | cheio de 10 cursos |
| R$ 5.100,00 | promo à vista de 10 cursos |
| R$ 255,00 | parcela promocional de 12 cursos |
| R$ 340,00 | parcela cheia de gestao-t5 e psicologia-hospitalar |
| R$ 8.100,00 | cheio de dialogo-aberto |
| R$ 6.075,00 | promo à vista de dialogo-aberto |
| R$ 303,75 | parcela promocional de dialogo-aberto |
| 20x | prazo de parcelamento de todos os 13 |

⚠️ R$ 2.100,00 (bônus vencido de Mulheridades) **não** entra na allowlist.

## Nota de escopo — pós ≠ congresso

| | congresso | pós |
|---|---|---|
| papel do agente | vender, gerar link de checkout | **informar e direcionar** |
| inscrição | compra direta (Doity) | **processo seletivo** (pré-aplicação → entrevista) |
| requisito | nenhum | **graduação concluída** (MEC) |
| checkout_url | sim | **não** |
| doity_event_id | sim | **não** (sync Doity e polling de conversão ignoram kind="pos") |
| certificado | 30h, emitido pelo CENAT | 360–390h, MEC, título de Especialista |
| contato do funil | atendimento@cenatcursos.com.br | processoseletivo@cenatsaudemental.com · (11) 95213-7432 |
