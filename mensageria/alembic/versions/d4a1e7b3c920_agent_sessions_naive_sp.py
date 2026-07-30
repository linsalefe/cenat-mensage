"""agent_sessions: last_inbound_at/last_outbound_at para timestamp naive (UTC-3)

Revision ID: d4a1e7b3c920
Revises: c3f8d2a94b61
Create Date: 2026-07-30

Corrige o bug que fazia o agente responder à PRIMEIRA mensagem de uma sessão e
emudecer para sempre depois.

`agent_sessions.last_inbound_at` era `timestamptz`, mas é alimentada por
`messages.timestamp`, que é `timestamp` naive na convenção UTC-3 do projeto.
Gravar naive na coluna aware funciona; o problema é a leitura de volta: o
SQLAlchemy devolve um datetime AWARE, e o handler usa esse valor como watermark
para filtrar `Message.timestamp > watermark` — uma coluna NAIVE. O asyncpg não
consegue codificar um aware para parâmetro de coluna naive e estoura
`DataError: can't subtract offset-naive and offset-aware datetimes`, abortando
`handle_inbound` antes de qualquer turno.

O primeiro turno escapava só porque a sessão nova tem `last_inbound_at IS NULL`
e o handler caía no fallback naive.

## Decisão coluna a coluna

Critério: migra a coluna que é COMPARADA com coluna naive; fica a que só
convive com valores aware.

| Coluna | Tipo antes | Comparada com naive? | Decisão |
|---|---|---|---|
| `agent_sessions.last_inbound_at` | timestamptz | **SIM** — `Message.timestamp` (handler.py) | **MIGRA** |
| `agent_sessions.last_outbound_at` | timestamptz | não hoje | **MIGRA** |
| `agent_sessions.created_at` / `updated_at` | timestamp | — | já naive, fica |
| `agent_followups.run_at` | timestamptz | não — só com `datetime.now(SP_TZ)` | **FICA** |
| `agent_followups.created_at` | timestamp | — | já naive, fica |
| `agent_turn_logs.created_at` | timestamp | — | já naive, fica |

`last_outbound_at` migra mesmo sem estar quebrada hoje: é o par simétrico de
`last_inbound_at` e a única escrita dela (`loop.py`) fica na mesma função que
grava a outra. Deixar as duas com tipos diferentes é como o bug reapareceria na
primeira vez que alguém comparasse a saída com `Message.timestamp`.

`agent_followups.run_at` FICA aware de propósito: é escrita e comparada
exclusivamente com `datetime.now(SP_TZ)` aware (`workers.py`, `tools_write.py`),
nunca encosta em coluna naive. Migrá-la seria mexer no worker de follow-up sem
necessidade — e follow-up é o caminho que dispara mensagem para cliente.

## Conversão do dado

O INSTANTE gravado está correto — só o tipo está errado. `AT TIME ZONE
'America/Sao_Paulo'` converte o timestamptz para a hora de parede de São Paulo,
que é exatamente a convenção de `messages.timestamp`. Na sessão 191:
`2026-07-30 17:28:20+00` → `2026-07-30 14:28:20`, batendo com a mensagem 4263.

O downgrade faz o caminho inverso pelo mesmo fuso, então é reversível sem perda.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4a1e7b3c920"
down_revision: Union[str, None] = "c3f8d2a94b61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SP = "America/Sao_Paulo"
COLUNAS = ("last_inbound_at", "last_outbound_at")


def upgrade() -> None:
    # timestamptz -> timestamp: pega a hora de parede em SP do instante gravado.
    for col in COLUNAS:
        op.execute(
            f"ALTER TABLE mensageria.agent_sessions "
            f"ALTER COLUMN {col} TYPE timestamp without time zone "
            f"USING {col} AT TIME ZONE '{SP}'"
        )


def downgrade() -> None:
    # timestamp -> timestamptz: reinterpreta a hora de parede como sendo de SP,
    # devolvendo o mesmo instante absoluto que havia antes do upgrade.
    for col in COLUNAS:
        op.execute(
            f"ALTER TABLE mensageria.agent_sessions "
            f"ALTER COLUMN {col} TYPE timestamp with time zone "
            f"USING {col} AT TIME ZONE '{SP}'"
        )
