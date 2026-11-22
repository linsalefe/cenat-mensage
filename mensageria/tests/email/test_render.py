#!/usr/bin/env python3
"""Placeholders, rodapé de descadastro, texto e MIME. Sem banco, sem rede.

Uso: .venv/bin/python tests/email/test_render.py   (exit 0 = ok)
"""
from __future__ import annotations

from _util import check, fim

from app.email.render import ensure_footer, html_to_text, interpolate, render_message  # noqa: E402
from app.email.ses import build_mime  # noqa: E402

print("interpolate")
ctx = {"nome": "Ana <b>", "email": "ana@x.com", "descadastro": "https://u/x?t=1&y=2"}
check(interpolate("Oi {nome}", ctx) == "Oi Ana <b>", "texto: sem escape")
check(interpolate("Oi {nome}", ctx, escape_html=True) == "Oi Ana &lt;b&gt;", "HTML: nome escapado")
check(interpolate("a { color: red }", ctx) == "a { color: red }", "CSS com chaves intacto")
check(interpolate("", ctx) == "", "vazio")
check("&amp;" in interpolate('<a href="{descadastro}">', ctx, escape_html=True), "URL escapada em atributo")

print("rodapé")
h = ensure_footer("<html><body><p>x</p></body></html>")
check("{descadastro}" in h and h.index("{descadastro}") < h.lower().index("</body>"),
      "rodapé antes de </body>")
check(ensure_footer("<p>x</p>").endswith("</div>"), "sem </body> → anexado no fim")
check(ensure_footer('<a href="{descadastro}">sair</a>') == '<a href="{descadastro}">sair</a>',
      "já tem {descadastro} → não duplica")

print("html_to_text")
t = html_to_text('<p>Olá</p><p>Veja <a href="https://x.com">aqui</a></p><style>p{}</style>')
check("Olá" in t and "aqui (https://x.com)" in t and "p{}" not in t, "strip com links")
check(html_to_text("a&amp;b<br>c") == "a&b\nc", "entidades e <br>")

print("render_message")
subj, html, text = render_message(
    subject="Oi {nome}\r\nBcc: x@y", html="<p>Oi {nome}</p>", text=None,
    nome="Bia", email="bia@x.com", unsubscribe_url="https://u/?t=abc",
)
check("\n" not in subj and "\r" not in subj, "assunto sem quebra de linha (header injection)")
check("https://u/?t=abc" in html, "HTML tem o link de descadastro")
check("https://u/?t=abc" in text, "texto gerado tem o link de descadastro")
_, _, text2 = render_message(subject="s", html="<p>x</p>", text="corpo", nome=None,
                             email="a@b.com", unsubscribe_url="https://u/?t=1")
check(text2.startswith("corpo") and "https://u/?t=1" in text2, "text_body próprio ganha rodapé")

print("MIME")
raw = build_mime(
    from_email="envio@mail.exemplo.com", from_name="CENAT Ação", to="ana@x.com", to_name="Ana",
    subject="Inscrição confirmada ✓", html="<p>é</p>", text="é", reply_to="r@x.com",
    headers={"List-Unsubscribe": "<https://u/?t=1>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
).decode("ascii")
check("List-Unsubscribe: <https://u/?t=1>" in raw, "List-Unsubscribe presente")
check("List-Unsubscribe-Post: List-Unsubscribe=One-Click" in raw, "List-Unsubscribe-Post presente")
check("multipart/alternative" in raw, "multipart/alternative")
check("Reply-To: r@x.com" in raw, "Reply-To")
check("\r\n" in raw, "line endings SMTP (CRLF)")

fim()
