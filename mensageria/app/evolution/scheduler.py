"""
Scheduler: converte dia/horário em linguagem natural para datetime.
Dispara ligações agendadas automaticamente.
"""
from datetime import datetime, timedelta, timezone
import re

SP_TZ = timezone(timedelta(hours=-3))

DIAS_SEMANA = {
    "segunda": 0, "segunda-feira": 0,
    "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1,
    "quarta": 2, "quarta-feira": 2,
    "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4,
    "sábado": 5, "sabado": 5,
    "domingo": 6,
    "hoje": -1,
    "amanhã": -2, "amanha": -2,
}


def parse_schedule_datetime(dia: str, horario: str) -> datetime | None:
    """Converte dia e horário em linguagem natural para datetime."""
    try:
        now = datetime.now(SP_TZ).replace(tzinfo=None)

        # Parsear horário
        hora = parse_time(horario)
        if hora is None:
            return None

        # Parsear dia
        dia_lower = dia.strip().lower()

        # Hoje
        if dia_lower == "hoje":
            target = now.replace(hour=hora[0], minute=hora[1], second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

        # Amanhã
        if dia_lower in ("amanhã", "amanha"):
            target = (now + timedelta(days=1)).replace(hour=hora[0], minute=hora[1], second=0, microsecond=0)
            return target

        # Dia da semana
        for nome, weekday in DIAS_SEMANA.items():
            if weekday < 0:
                continue
            if nome in dia_lower:
                days_ahead = weekday - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                target = (now + timedelta(days=days_ahead)).replace(
                    hour=hora[0], minute=hora[1], second=0, microsecond=0
                )
                return target

        # Tentar formato de data (20/02, 20/02/2026)
        date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?', dia_lower)
        if date_match:
            d = int(date_match.group(1))
            m = int(date_match.group(2))
            y = int(date_match.group(3)) if date_match.group(3) else now.year
            if y < 100:
                y += 2000
            target = datetime(y, m, d, hora[0], hora[1])
            if target < now:
                target = target.replace(year=target.year + 1)
            return target

        return None

    except Exception as e:
        print(f"❌ Erro parse_schedule_datetime: {e}")
        return None


def parse_time(horario: str) -> tuple | None:
    """Converte horário em linguagem natural para (hora, minuto)."""
    if not horario:
        return None

    horario = horario.strip().lower()

    # "14:30", "14h30", "14h", "14 horas", "2 da tarde"
    match = re.search(r'(\d{1,2})\s*[h:]\s*(\d{2})?', horario)
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        return validate_time(h, m)

    # "9 horas", "10 horas"
    match = re.search(r'(\d{1,2})\s*hora', horario)
    if match:
        h = int(match.group(1))
        return validate_time(h, 0)

    # "2 da tarde", "3 da tarde"
    match = re.search(r'(\d{1,2})\s*da\s*tarde', horario)
    if match:
        h = int(match.group(1)) + 12
        return validate_time(h, 0)

    # "9 da manhã"
    match = re.search(r'(\d{1,2})\s*da\s*manh', horario)
    if match:
        h = int(match.group(1))
        return validate_time(h, 0)

    # Só número
    match = re.search(r'(\d{1,2})', horario)
    if match:
        h = int(match.group(1))
        return validate_time(h, 0)

    return None


def validate_time(h: int, m: int) -> tuple | None:
    """Valida se o horário está entre 06h e 23h."""
    if h < 6 or h > 23:
        return None
    if m < 0 or m > 59:
        return None
    return (h, m)