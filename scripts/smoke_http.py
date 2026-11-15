import json
import os
from pathlib import Path
import secrets
import sys
import threading
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from wsgiref.simple_server import make_server, WSGIRequestHandler

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["DJANGO_SETTINGS_MODULE"] = "reservastoresupa.core.test_settings"
from django.conf import settings
settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "file:reservastore_http_smoke?mode=memory&cache=shared", "OPTIONS": {"uri": True}}}
settings.ALLOWED_HOSTS = ["127.0.0.1"]
import django
django.setup()
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.contrib.auth import get_user_model
call_command("migrate", interactive=False, verbosity=0)
password = secrets.token_urlsafe(30)
get_user_model().objects.create_superuser("smoke-admin", "smoke-admin@example.test", password)

class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass

server = make_server("127.0.0.1", 0, get_wsgi_application(), handler_class=QuietHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_port}/api/"
checks = []

def request(method, path, body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as response:
            status, raw = response.status, response.read()
    except HTTPError as error:
        status, raw = error.code, error.read()
    assert status == expected, f"{method} {path}: expected {expected}, got {status}"
    checks.append(f"{method} {path}: {status}")
    return json.loads(raw) if raw else None

try:
    for username, papel in [("smoke-customer", "cliente"), ("smoke-other", "cliente"), ("smoke-merchant", "lojista")]:
        request("POST", "auth/cadastro/", {"username": username, "password": password, "email": username+"@example.test", "first_name": "Synthetic", "telefone": "00000000", "papel": papel}, expected=201)
    def login(username):
        return request("POST", "token/", {"username": username, "password": password})
    customer = login("smoke-customer")
    other = login("smoke-other")
    merchant = login("smoke-merchant")
    admin = login("smoke-admin")
    loja = request("POST", "lojas/", {"nome": "Synthetic shop", "whatsapp": "00000000"}, merchant["access"], 201)["id"]
    request("PATCH", f"lojas/{loja}/", {"aberta": True}, merchant["access"])
    assert request("GET", "catalogo/lojas/") == []
    categoria = request("POST", "categorias/", {"nome": "Synthetic category"}, merchant["access"], 201)["id"]
    produto = request("POST", "produtos/", {"nome": "Synthetic product", "categoria": categoria, "preco": "8.25"}, merchant["access"], 201)["id"]
    area = request("POST", "lojista/areas-entrega/", {"condominio": "Synthetic condo", "taxa": "2.50", "prazo_estimado_minutos": 25}, merchant["access"], 201)["id"]
    request("PATCH", f"administracao/lojas/{loja}/", {"ativa": True, "assinatura_status": "ativa", "mensalidade": None}, admin["access"])
    assert request("GET", f"catalogo/lojas/{loja}/produtos/")[0]["id"] == produto
    assert request("GET", "catalogo/lojas/?page=1&page_size=1")["count"] == 1
    assert request("GET", f"catalogo/lojas/{loja}/produtos/?page=1&page_size=1")["results"][0]["id"] == produto
    assert request("GET", f"catalogo/lojas/{loja}/areas-entrega/")[0]["prazo_estimado_minutos"] == 25
    request("GET", "administracao/usuarios/?page=1", token=customer["access"], expected=403)
    endereco = request("POST", "enderecos/", {"condominio": "Synthetic condo", "bloco": "A", "apartamento": "101", "destinatario": "Synthetic", "telefone": "00000000"}, customer["access"], 201)["id"]
    request("POST", f"carrinhos/{loja}/itens/", {"produto": produto, "quantidade": 2}, customer["access"], 201)
    payload = {"loja": loja, "endereco": endereco, "area_entrega": area, "meio_pagamento": "pix", "chave_checkout": str(uuid.uuid4())}
    preview = request("POST", "pedidos/previa/", {key: value for key, value in payload.items() if key != "chave_checkout"}, customer["access"])
    assert preview["total"] == "19.00" and preview["prazo_estimado_minutos"] == 25
    assert request("GET", "pedidos/", token=customer["access"]) == []
    assert len(request("GET", f"carrinhos/{loja}/", token=customer["access"])["itens"]) == 1
    pedido = request("POST", "pedidos/", payload, customer["access"], 201)
    assert pedido["total"] == "19.00"
    pk = pedido["id"]
    assert pedido["prazo_estimado_minutos"] == 25
    request("PATCH", f"lojista/areas-entrega/{area}/", {"prazo_estimado_minutos": 45}, merchant["access"])
    assert request("GET", f"pedidos/{pk}/", token=customer["access"])["prazo_estimado_minutos"] == 25
    assert request("POST", "pedidos/", payload, customer["access"])["id"] == pk
    request("GET", f"pedidos/{pk}/", token=other["access"], expected=404)
    request("POST", f"pedidos/{pk}/informar-pagamento/", {}, customer["access"])
    request("POST", f"lojista/pedidos/{pk}/pagamento/", {"status": "confirmado"}, merchant["access"])
    for state in ("aceito", "preparando", "saiu_entrega", "entregue"):
        request("POST", f"lojista/pedidos/{pk}/transicao/", {"status": state}, merchant["access"])
    request("POST", "conta/senha/", {"senha_atual": password, "nova_senha": secrets.token_urlsafe(30)}, customer["access"])
    request("GET", "conta/", token=customer["access"], expected=401)
    request("POST", "token/refresh/", {"refresh": customer["refresh"]}, expected=401)
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else root / ".local/http-smoke.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("HTTP local real: PASS\nSQLite nomeado em memoria; dados sinteticos; nenhum banco remoto.\n" + "\n".join(checks) + f"\n{len(checks)} requisicoes verificadas. Servidor encerrado ao finalizar.\n", encoding="utf-8")
    print(f"HTTP smoke PASS: {len(checks)} requests; server shut down; no persistent database.")
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
