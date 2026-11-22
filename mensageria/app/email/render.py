"""Conteúdo do e-mail: placeholders, rodapé de descadastro e versão texto.

Placeholders (mesma semântica do `{nome}` do broadcast de WhatsApp):
  {nome}        nome do destinatário (vazio se não houver)
  {email}       e-mail do destinatário
  {descadastro} URL de descadastro

Substituição por `str.replace`, não `str.format`: HTML de e-mail tem CSS com
chaves (`a { color: … }`) que o format quebraria.
"""
from __future__ import annotations

import html as _html
import re

PH_NOME = "{nome}"
PH_EMAIL = "{email}"
PH_DESCADASTRO = "{descadastro}"

FOOTER_HTML = (
    '<div style="margin-top:32px;padding-top:16px;border-top:1px solid #e5e5e5;'
    'font-family:Arial,sans-serif;font-size:12px;line-height:1.5;color:#777777;">'
    "Você recebeu este e-mail porque se cadastrou ou comprou com o CENAT. "
    'Para não receber mais, <a href="{descadastro}" style="color:#777777;">'
    "descadastre-se aqui</a>."
    "</div>"
)
FOOTER_TEXT = "\n\n--\nPara não receber mais e-mails do CENAT: {descadastro}\n"


def interpolate(text: str, ctx: dict, *, escape_html: bool = False) -> str:
    """Troca {nome}/{email}/{descadastro}. Com escape_html, nome e e-mail são
    escapados (vêm de CSV/cadastro — não podem injetar HTML)."""
    if not text:
        return ""
    nome = ctx.get("nome") or ""
    email = ctx.get("email") or ""
    url = ctx.get("descadastro") or ""
    if escape_html:
        nome, email, url = _html.escape(nome), _html.escape(email), _html.escape(url, quote=True)
    return text.replace(PH_NOME, nome).replace(PH_EMAIL, email).replace(PH_DESCADASTRO, url)


def ensure_footer(html: str) -> str:
    """Garante o link de descadastro: se o HTML não tem {descadastro}, anexa o
    rodapé padrão (antes de </body> quando houver). Rode ANTES de interpolate."""
    html = html or ""
    if PH_DESCADASTRO in html:
        return html
    m = re.search(r"</body\s*>", html, flags=re.IGNORECASE)
    if m:
        return html[: m.start()] + FOOTER_HTML + html[m.start():]
    return html + FOOTER_HTML


def ensure_footer_text(text: str) -> str:
    text = text or ""
    if PH_DESCADASTRO in text:
        return text
    return text.rstrip() + FOOTER_TEXT


def html_to_text(html: str) -> str:
    """Strip simples de HTML → texto. Links viram `texto (url)`."""
    if not html:
        return ""
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1\s*>", "", html)
    s = re.sub(
        r'(?is)<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a\s*>',
        lambda m: f"{re.sub(r'<[^>]+>', '', m.group(2)).strip()} ({m.group(1)})",
        s,
    )
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|table)\s*>", "\n", s)
    s = re.sub(r"(?i)<li\b[^>]*>", "- ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def render_message(
    *, subject: str, html: str, text: str | None, nome: str | None, email: str, unsubscribe_url: str
) -> tuple[str, str, str]:
    """(subject, html, text) finais para um destinatário."""
    ctx = {"nome": nome or "", "email": email, "descadastro": unsubscribe_url}
    html_tpl = ensure_footer(html)
    text_tpl = ensure_footer_text(text) if (text or "").strip() else None
    final_html = interpolate(html_tpl, ctx, escape_html=True)
    if text_tpl is not None:
        final_text = interpolate(text_tpl, ctx)
    else:
        final_text = html_to_text(final_html)
    # Assunto: só nome/e-mail, e sem quebra de linha (header injection).
    final_subject = interpolate(subject or "", {**ctx, "descadastro": ""})
    final_subject = re.sub(r"[\r\n]+", " ", final_subject).strip()
    return final_subject, final_html, final_text
