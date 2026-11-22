"""Canal de e-mail via Amazon SES (Etapa E4a — docs/funis/EMAIL_SES.md).

Módulo isolado do WhatsApp: tabelas, worker e rotas próprios. A única porta de
saída de e-mail é `app.email.service.send_one` (supressão → sandbox → cota → SES).
"""
