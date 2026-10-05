"""Prueba desde afuera, como la haría el profesor: firma con el código de la clase y llama a cada ruta.

Uso (con la app corriendo):
    python tests/prueba_profesor.py                              # contra http://localhost:8000
    python tests/prueba_profesor.py https://abcd-12-34.ngrok-free.app
    python tests/prueba_profesor.py URL --key mi_llave_privada_123

Solo usa la biblioteca estándar. Crea y borra su propio producto (no toca el menú real) y deja
transacciones de prueba en la base (MongoDB o memoria) (las ve en /antifraude; se borran con tests/e2e_fraud_http.py --clean).
Cada línea muestra el `id` de la petición: búsquelo en /logs para ver qué respondió la app y por qué.
"""

import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request
import uuid

args = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = (args[0] if args else "http://127.0.0.1:8000").rstrip("/")  # en Windows "localhost" prueba IPv6 primero y tarda ~2 s por petición
KEY = sys.argv[sys.argv.index("--key") + 1].encode() if "--key" in sys.argv else b"mi_llave_privada_123"
RUN = uuid.uuid4().hex[:6]
PASSED, FAILED = [], []


def call(method, path, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    headers = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"null"), resp.headers.get("X-Request-Id")
    except urllib.error.HTTPError as err:
        text = err.read()
        try:
            return err.code, json.loads(text or b"null"), err.headers.get("X-Request-Id")
        except ValueError:
            return err.code, {"mensaje": text[:200].decode("utf-8", "replace")}, err.headers.get("X-Request-Id")


def sign(payload, key=None):
    """El código de la diapositiva: JSON determinista + HMAC-SHA256."""
    datos = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key or KEY, datos.encode("utf-8"), hashlib.sha256).hexdigest()


def check(name, result, status, motivo=None, needs_message=True):
    code, body, request_id = result
    body = body if isinstance(body, (dict, list)) else {}
    explained = (not needs_message) or (isinstance(body, dict) and bool(body.get("mensaje") or body.get("detail") or body.get("ok")))
    ok = code == status and (motivo is None or (isinstance(body, dict) and body.get("motivo") == motivo)) and explained
    (PASSED if ok else FAILED).append(name)
    said = body.get("mensaje") if isinstance(body, dict) else ""
    print(f"  {'OK   ' if ok else 'FALLA'} {name:<46} HTTP {code:<3} id={request_id}" + ("" if ok else f"  esperaba {status} {motivo or ''} :: {str(said)[:120]}"))
    return body


def accepted(name, result, status=201):
    """201 y además aceptada (VALID o SUSPICIOUS): con rejected_as_201 una errónea también responde 201."""
    body = check(name, result, status)
    good = isinstance(body, dict) and body.get("estado") in ("VALID", "SUSPICIOUS")
    if not good:
        FAILED.append(name + " (quedó como errónea)")
        motivo = body.get("motivo") if isinstance(body, dict) else ""
        print(f"  FALLA {name} quedó como errónea: {motivo}")
    return body


def tx(n, **over):
    t = {"idTxn": f"PROF{RUN}-{n}", "user": f"profe{RUN}@correo.com", "date": "2026-10-03T10:30:%02d.120" % n,
         "value": 50000, "paymentMethod": "Tarjeta"}
    t.update(over)
    return t


def main():
    print(f"Probando {BASE} (llave: huella {hashlib.sha256(KEY).hexdigest()[:12]})\n")
    status, health, _ = call("GET", "/api/health")
    if status != 200:
        sys.exit(f"No se pudo conectar con {BASE}/api/health ({status}). ¿Está corriendo la app / el túnel?")
    mongo_ok = health.get("mongodb") == "ok"
    print(f"  MongoDB: {health.get('mongodb')}" + ("" if mongo_ok else " (los datos de las pruebas de transacciones quedan solo en memoria)"))
    # Con APPRESSO_REJECTED_AS_201=true (por defecto) una transacción recibida que queda RECHAZADA responde 201
    # (el resultado va en el cuerpo); con false responde 422 / 400. Se toma de /api/config.
    _, cfg, _ = call("GET", "/api/config")
    as_201 = bool(isinstance(cfg, dict) and cfg.get("rejected_as_201"))
    lenient = bool(isinstance(cfg, dict) and cfg.get("lenient_inputs"))
    REJ, BAD = (201, 201) if as_201 else (422, 400)
    print(f"  Rechazadas responden {REJ}/{BAD} (rejected_as_201={as_201}); modo generador externo: {lenient}")

    print("\n== Hash HMAC-SHA256 (diapositiva) ==")
    slide = {"id": 1001, "producto": "Mouse", "cantidad": 4, "valor": 50000}
    body = check("calcular hash de la diapositiva", call("POST", "/api/hash/calcular", slide), 200)
    check("el servidor calcula el mismo hash que la clase", (200 if body.get("hash") == sign(slide) else 0, {"ok": True}, None), 200)
    check("verificar: datos intactos -> ACEPTADA", call("POST", "/api/hash/verificar", dict(slide, hash=sign(slide))), 200)
    body = check("verificar: dato alterado -> RECHAZADA", call("POST", "/api/hash/verificar", dict(slide, cantidad=3, hash=sign(slide))), 422, "HASH_MISMATCH")
    check("   y explica la causa", (200 if body.get("diagnostico_hash", {}).get("causa_probable") else 0, {"ok": True}, None), 200)
    check("verificar: sin hash", call("POST", "/api/hash/verificar", slide), 422, "HASH_REQUERIDO")
    check("verificar: hash mal formado", call("POST", "/api/hash/verificar", dict(slide, hash="abc")), 422, "INVALID_HASH_FORMAT")

    if True:  # funciona con MongoDB o en modo memoria
        print("\n== POST /api/transactions ==")
        t = tx(1)
        check("transacción firmada con la llave de la clase", call("POST", "/api/transactions", dict(t, hash=sign(t))), 201)
        t = tx(2, nombre="Profe Prueba", cedula="1012345678", value="50000", paymentMethod="tarjeta")
        check("con nombre/cédula, valor texto y método en minúscula", call("POST", "/api/transactions", dict(t, hash=sign(t))), 201)
        t = tx(3)
        check("sin hash: el servidor lo genera", call("POST", "/api/transactions", t), 201)
        t = tx(4)
        body = check("datos alterados -> HASH_MISMATCH (REJECTED)", call("POST", "/api/transactions", dict(t, value=1, hash=sign(t))), REJ, "HASH_MISMATCH")
        check("   y explica la causa", (200 if body.get("diagnostico_hash") else 0, {"ok": True}, None), 200)
        check("   y queda clasificada como REJECTED", (200 if body.get("estado") == "REJECTED" else 0, {"ok": True}, None), 200)
        t = tx(5)
        check("firmada con otra llave -> explica cuál", call("POST", "/api/transactions", dict(t, hash=sign(t, b"otra_llave"))), REJ, "HASH_MISMATCH")
        t = tx(6, idTxn=f"PROF{RUN}-1")
        check("ID duplicado", call("POST", "/api/transactions", t), 409, "DUPLICATE_TRANSACTION")
        check("valor 'abc' (nunca 0)", call("POST", "/api/transactions", tx(7, value="abc")), REJ, "INVALID_VALUE")
        body = check("faltan campos -> dice qué se espera", call("POST", "/api/transactions", {"id": 1}), REJ, "NULL_FIELD")
        check("   y trae el formato esperado", (200 if "formato_esperado" in body else 0, {"ok": True}, None), 200)
        body = check("JSON mal formado", call("POST", "/api/transactions", raw=b'{"idTxn": 1,'), BAD, "MALFORMED_JSON")
        check("   y queda en la cuarentena", (200 if body.get("id_invalida") else 0, {"ok": True}, None), 200)
        check("cuerpo vacío", call("POST", "/api/transactions", raw=b""), BAD, "MALFORMED_JSON")

        print("\n== Formatos de un generador externo ==")
        accepted("rutas alias /api/transacciones", call("POST", "/api/transacciones", tx(8)), 201)
        accepted("ruta alias /transacciones", call("POST", "/transacciones", tx(9, idTxn=f"PROF{RUN}-9")), 201)
        t = tx(10, idTxn=f"PROF{RUN}-10")
        accepted("UTF-8 con BOM", call("POST", "/api/transactions", raw=b"\xef\xbb\xbf" + json.dumps(t).encode()), 201)
        t = tx(11, idTxn=f"PROF{RUN}-11")
        accepted("UTF-16 (PowerShell)", call("POST", "/api/transactions", raw=json.dumps(t).encode("utf-16")), 201)
        accepted("JSON doblemente codificado", call("POST", "/api/transactions", raw=json.dumps(json.dumps(tx(12, idTxn=f"PROF{RUN}-12"))).encode()), 201)
        body = check("lote de 3 (una lista)", call("POST", "/api/transactions", [tx(13, idTxn=f"PROF{RUN}-13"), tx(14, idTxn=f"PROF{RUN}-14"), tx(15, idTxn=f"PROF{RUN}-15", value=None)]), 201)
        check("   y el lote separa buenas de erróneas", (200 if (body.get("aceptadas"), body.get("rechazadas")) == (2, 1) else 0, {"ok": True}, None), 200)
        if lenient:
            t = tx(16, idTxn=f"PROF{RUN}-16", user="25", paymentMethod="Crédito")
            accepted("user como id y método libre", call("POST", "/api/transactions", t), 201)
            t = tx(17, idTxn=f"PROF{RUN}-17")
            plano = hashlib.sha256(json.dumps(t, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            accepted("hash SHA-256 sin llave", call("POST", "/api/transactions", dict(t, hash=plano)), 201)

        print("\n== Cuarentena y consultas ==")
        check("listar peticiones erróneas", call("GET", "/api/transactions/invalid"), 200, needs_message=False)
        check("consultar historial", call("GET", f"/api/transactions?usuario=profe{RUN}@correo.com"), 200, needs_message=False)
        check("verificar integridad guardada", call("GET", f"/api/transactions/PROF{RUN}-1/verify"), 200, needs_message=False)
        check("ventana deslizante", call("GET", "/api/window"), 200, needs_message=False)
        check("logs de negocio", call("GET", "/api/logs?limit=5"), 200, needs_message=False)

    print("\n== Productos: GET / POST / PUT / PATCH / DELETE ==")
    check("GET lista", call("GET", "/api/productos"), 200, needs_message=False)
    body = check("POST crear", call("POST", "/api/productos", {"nombre": f"Monitor {RUN}", "precio": 800000}), 201)
    pid = (body.get("producto") or {}).get("id")
    if pid is None:
        print("  (no se pudo crear el producto: se omiten las pruebas con id)")
    else:
        check("GET uno", call("GET", f"/api/productos/{pid}"), 200, needs_message=False)
        check("POST precio 'abc' -> rechazado", call("POST", "/api/productos", {"nombre": "Otro", "precio": "abc"}), 422, "INVALID_VALUE")
        check("POST nombre repetido -> 409", call("POST", "/api/productos", {"nombre": f"MONITOR {RUN}", "precio": 1}), 409, "NOMBRE_DUPLICADO")
        check("PUT reemplaza completo", call("PUT", f"/api/productos/{pid}", {"nombre": f"Monitor {RUN}", "precio": 850000, "categoria": "Tecnología"}), 200)
        check("PUT incompleto -> pide todo", call("PUT", f"/api/productos/{pid}", {"precio": 1}), 422, "NULL_FIELD")
        body = check("PATCH solo el precio", call("PATCH", f"/api/productos/{pid}", {"precio": 60000}), 200)
        check("   conserva el resto", (200 if (body.get("producto") or {}).get("categoria") == "Tecnología" else 0, {"ok": True}, None), 200)
        patch = {"precio": 65000}
        check("PATCH con hash válido", call("PATCH", f"/api/productos/{pid}", dict(patch, hash=sign(patch))), 200)
        check("PATCH con hash inválido", call("PATCH", f"/api/productos/{pid}", {"precio": 1, "hash": "0" * 64}), 422, "HASH_MISMATCH")
        check("PATCH vacío", call("PATCH", f"/api/productos/{pid}", {}), 422, "SIN_CAMBIOS")
        check("DELETE", call("DELETE", f"/api/productos/{pid}"), 200)
        check("GET borrado -> 404 explicado", call("GET", f"/api/productos/{pid}"), 404)
    check("id que no es número -> explicado", call("GET", "/api/productos/abc"), 422, "PARAMETRO_INVALIDO")

    print("\n== Análisis y descomposición (totales) ==")
    body = check("total de la diapositiva", call("POST", "/api/totales", {"productos": [
        {"producto": "Mouse", "valor": "50000", "cantidad": "2"}, {"producto": "Teclado", "valor": 80000, "cantidad": 1}]}), 200)
    check("   Total: $180000", (200 if body.get("total") == 180000 else 0, {"ok": True}, None), 200)
    body = check("productos inválidos se informan", call("POST", "/api/totales", {"productos": [
        {"producto": "X", "valor": -1, "cantidad": 1}, {"producto": "Y", "valor": 5, "cantidad": 2}]}), 200)
    check("   y no tumban el total", (200 if body.get("total") == 10 and len(body.get("invalidos", [])) == 1 else 0, {"ok": True}, None), 200)

    print("\n== Errores explicados ==")
    check("ruta inexistente", call("GET", "/ruta/inexistente"), 404, "NO_EXISTE")
    check("método no permitido", call("DELETE", "/api/transactions"), 405, "METODO_NO_PERMITIDO")
    check("índice de rutas", call("GET", "/api"), 200, needs_message=False)
    check("API de logs HTTP", (call("GET", "/api/logs/http?limit=1")[0], {"ok": True}, None), 200)

    print(f"\nResultado: {len(PASSED)} OK, {len(FAILED)} con fallas.  Logs en vivo: {BASE}/logs")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
