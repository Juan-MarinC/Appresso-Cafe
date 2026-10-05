"""Compatibilidad con clientes externos que llegan por ngrok (o cualquier proxy): bots de Telegram,
Postman, PowerShell, navegadores de otro dominio, generadores que mandan ráfagas o lotes.

Uso (con la app corriendo):
    python tests/prueba_clientes_externos.py                         # contra http://localhost:8000 simulando ngrok
    python tests/prueba_clientes_externos.py https://xxxx.ngrok-free.app   # contra el túnel real

En local agrega los encabezados que pone ngrok (Host *.ngrok-free.app, X-Forwarded-For/Proto/Host) para
reproducir lo que ve la app cuando el profesor se conecta desde afuera. Solo usa la biblioteca estándar.
Deja transacciones de prueba en la base (se ven en /antifraude).
"""

import http.client
import json
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlencode, urlsplit

TARGET = next((a for a in sys.argv[1:] if a.startswith("http")), "http://localhost:8000").rstrip("/")
URL = urlsplit(TARGET)
REMOTE = "localhost" not in URL.netloc and "127.0.0.1" not in URL.netloc
RUN = uuid.uuid4().hex[:6]
NGROK_HOST = f"prueba-{RUN}.ngrok-free.app"
PASSED, FAILED = [], []
_ids = iter(range(1, 10**6))
_ids_lock = threading.Lock()


def new_id(prefix="EXT"):
    with _ids_lock:
        return f"{prefix}{RUN}-{next(_ids)}"


def proxy_headers(extra=None):
    headers = {"ngrok-skip-browser-warning": "1"}
    if not REMOTE:  # lo que agrega el agente de ngrok al reenviar a localhost:8000
        headers.update({"Host": NGROK_HOST, "X-Forwarded-For": "181.51.10.20", "X-Forwarded-Proto": "https", "X-Forwarded-Host": NGROK_HOST})
    headers.update(extra or {})
    return headers


def call(method, path, body=None, headers=None, timeout=60):
    conn_cls = http.client.HTTPSConnection if URL.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(URL.netloc, timeout=timeout)
    started = time.perf_counter()
    try:
        conn.request(method, path, body=body, headers=proxy_headers(headers))
        resp = conn.getresponse()
        raw = resp.read()
        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = {"_texto": raw[:200].decode("utf-8", "replace")}
        return resp.status, data, dict(resp.getheaders()), round(time.perf_counter() - started, 2)
    finally:
        conn.close()


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name)
    print(("  OK    " if ok else "  FALLA ") + name + ("" if ok else f"  -> {detail}"))


def txn(**over):
    """Cada transacción con su propio usuario: así un caso de formato no dispara la ventana de otro."""
    id_txn = new_id()
    data = {"idTxn": id_txn, "user": f"{id_txn.lower()}@correo.com", "date": datetime.now().isoformat(timespec="milliseconds"),
            "value": 25000, "paymentMethod": "Tarjeta"}
    data.update(over)
    return data


def jpost(payload, path="/api/transactions", content_type="application/json", encoding="utf-8", extra=None):
    body = payload if isinstance(payload, (bytes, str)) else json.dumps(payload, ensure_ascii=False)
    if isinstance(body, str):
        body = body.encode(encoding)
    headers = {"Content-Type": content_type} if content_type else {}
    headers.update(extra or {})
    return call("POST", path, body, headers)


def estado(data):
    return (data or {}).get("estado")


def main():
    print(f"Probando {TARGET} {'(túnel real)' if REMOTE else f'simulando ngrok: Host {NGROK_HOST}'}\n")

    print("== Conexión a través del proxy ==")
    s, d, h, _ = call("GET", "/api/health")
    check("GET /api/health responde 200 con JSON", s == 200 and isinstance(d, dict), (s, d))
    check("cada respuesta trae X-Request-Id (para buscarla en /logs)", any(k.lower() == "x-request-id" for k in h), h)
    s, d, h, _ = call("HEAD", "/api/health")
    check("HEAD /api/health (monitores de disponibilidad)", s in (200, 204), (s, d))
    s, d, h, _ = call("GET", "/api/transactions/?limit=1")
    check("GET /api/transactions/ con '/' final", s == 200 and isinstance(d, list), (s, d))
    s, d, h, _ = call("GET", "/api/anomalies/?limit=1")
    location = next((v for k, v in h.items() if k.lower() == "location"), "")
    check("una redirección por '/' final conserva https:// detrás del proxy",
          s == 200 or (s in (301, 302, 307, 308) and (location.startswith("https://") or location.startswith("/"))), (s, location))

    print("\n== Navegador desde otro dominio (CORS: páginas web, Hoppscotch, apps JS) ==")
    origin = {"Origin": "https://herramienta-del-profesor.example"}
    s, d, h, _ = call("OPTIONS", "/api/transactions", headers={**origin, "Access-Control-Request-Method": "POST",
                                                                "Access-Control-Request-Headers": "content-type"})
    acao = next((v for k, v in h.items() if k.lower() == "access-control-allow-origin"), None)
    check("preflight OPTIONS permitido", s in (200, 204) and acao in ("*", origin["Origin"]), (s, acao, d))
    s, d, h, _ = jpost(txn(), extra=origin)
    acao = next((v for k, v in h.items() if k.lower() == "access-control-allow-origin"), None)
    check("POST desde otro dominio trae Access-Control-Allow-Origin", s == 201 and acao in ("*", origin["Origin"]), (s, acao))

    print("\n== Formatos de distintos clientes ==")
    s, d, _, _ = jpost(txn(), extra={"User-Agent": "python-requests/2.32"})
    check("Python requests (JSON)", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(txn(nombre="Belén Muñoz"), encoding="cp1252", extra={"User-Agent": "Mozilla/5.0 (Windows NT; Windows NT 10.0) WindowsPowerShell/5.1"})
    check("PowerShell 5.1 con tildes (Windows-1252)", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(txn(), content_type="application/json; charset=utf-8")
    check("Content-Type con charset", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(txn(), content_type="text/plain")
    check("JSON enviado como text/plain (fetch sin encabezado)", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(txn(), content_type=None)
    check("JSON sin Content-Type", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(urlencode(txn()), content_type="application/x-www-form-urlencoded")
    check("formulario x-www-form-urlencoded", s == 201 and estado(d) == "VALID", (s, d))

    boundary = "----PostmanBoundary" + RUN
    parts = "".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in txn().items())
    s, d, _, _ = jpost(parts + f"--{boundary}--\r\n", content_type=f"multipart/form-data; boundary={boundary}")
    check("multipart/form-data (pestaña form-data de Postman)", s == 201 and estado(d) == "VALID", (s, d))

    query = urlencode(txn())
    s, d, _, _ = call("POST", f"/api/transactions?{query}", b"", {"Content-Length": "0"})
    check("datos en la query string sin cuerpo (requests.post(url, params=...))", s == 201 and estado(d) == "VALID", (s, d))

    s, d, _, _ = jpost(txn(date=int(time.time())))
    check("fecha en segundos epoch (como manda Telegram)", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(txn(date=int(time.time() * 1000)))
    check("fecha en milisegundos epoch (Date.now() de JavaScript)", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(txn(date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    check("fecha 'AAAA-MM-DD HH:MM:SS' (con espacio)", s == 201 and estado(d) == "VALID", (s, d))
    s, d, _, _ = jpost(txn(date=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")))
    check("fecha ISO en UTC con 'Z'", s == 201 and estado(d) == "VALID", (s, d))

    print("\n== Bot de Telegram ==")
    update = {"update_id": 900000001, "message": {"message_id": 7, "date": int(time.time()), "text": "/pagar 25000",
              "from": {"id": 123456789, "is_bot": False, "first_name": "Profe"}, "chat": {"id": 123456789, "type": "private"}}}
    s, d, _, secs = jpost(update, extra={"User-Agent": "TelegramBot (like TwitterBot)"})
    check("webhook de Telegram (Update) responde 2xx sin romperse", 200 <= s < 300 and secs < 10, (s, secs, d))
    check("   y no se acepta como transacción", estado(d) == "REJECTED", d)
    chat_id = 100000000 + int(RUN, 16) % 900000000  # distinto en cada corrida: si se repite, la regla nocturna lo marca
    s, d, _, _ = jpost(txn(user=str(chat_id), paymentMethod="Nequi"), extra={"User-Agent": "python-telegram-bot/21.0"})
    check("bot que reenvía una compra con su chat_id como usuario", s == 201 and estado(d) == "VALID", (s, d))

    print("\n== Entradas raras que no deben tumbar la app ==")
    for name, body, ctype in [
        ("cuerpo binario", bytes(range(256)) * 4, "application/octet-stream"),
        ("JSON truncado", b'{"idTxn": "X1", "user": ', "application/json"),
        ("texto plano", "hola profe".encode(), "text/plain"),
        ("lista de textos", b'["a", "b"]', "application/json"),
        ("número suelto", b"42", "application/json"),
        ("nombre de 20.000 caracteres", json.dumps(txn(nombre="A" * 20000)).encode(), "application/json"),
    ]:
        s, d, _, _ = jpost(body, content_type=ctype)
        check(f"{name}: responde sin error del servidor", s < 500 and isinstance(d, dict), (s, d))
    s, d, _, secs = jpost(b'{"pad": "' + b"x" * 2_000_000 + b'"}')
    check("cuerpo de 2 MB: responde sin colgarse", s < 500 and secs < 30, (s, secs))

    print("\n== Ráfagas y lotes (bots) ==")
    users = [f"rafaga{i}-{RUN}@correo.com" for i in range(20)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda u: jpost(txn(user=u)), users * 2))
    secs = round(time.perf_counter() - started, 1)
    codes = sorted({r[0] for r in results})
    check(f"40 peticiones en paralelo: ninguna falla ({secs} s)", codes == [201], codes)
    one = f"bot-{RUN}@correo.com"
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: jpost(txn(user=one)), range(10)))
    states = [estado(r[1]) for r in results]
    check("10 en paralelo del mismo usuario: se detecta la ráfaga", states.count("SUSPICIOUS") >= 7 and all(r[0] == 201 for r in results), states)
    s, d, _, secs = jpost([txn() for _ in range(50)])
    check(f"lote de 50 en una sola petición ({secs} s)", s == 201 and (d or {}).get("total") == 50 and secs < 30, (s, secs))
    s, d, _, secs = jpost([txn() for _ in range(1500)])
    check(f"lote gigante (1500): se responde a tiempo, no se cuelga ({secs} s)", s < 500 and secs < 30, (s, secs, (d or {}).get("mensaje")))

    print("\n== Reintentos (el cliente no recibió la respuesta y reenvía) ==")
    same = txn()
    first = jpost(same)
    again = jpost(same)
    check("el reenvío idéntico no crea otra transacción", first[0] == 201 and again[0] in (200, 201, 409), (first[0], again[0], again[1]))
    check("   y la respuesta explica que ya estaba registrada", "regist" in json.dumps(again[1], ensure_ascii=False).lower() or "exist" in json.dumps(again[1], ensure_ascii=False).lower(), again[1])

    print(f"\nResultado: {len(PASSED)} OK, {len(FAILED)} con fallas.")
    sys.exit(1 if FAILED else 0)


main()
