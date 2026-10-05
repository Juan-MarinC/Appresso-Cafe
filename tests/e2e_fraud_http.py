"""Prueba de punta a punta del módulo antifraude contra el servidor y MongoDB REALES.

Uso (con la app corriendo):
    venv\\Scripts\\python.exe tests\\e2e_fraud_http.py [http://localhost:8000]

Cada ejecución usa usuarios e IDs únicos, así que se puede repetir sin colisiones.
Deja los datos en MongoDB (se ven en /antifraude); para borrarlos: `--clean`.
No se llama test_*.py a propósito: `unittest discover` no la ejecuta porque necesita servidor.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta

BASE = next((a for a in sys.argv[1:] if a.startswith("http")), "http://127.0.0.1:8000")  # "localhost" tarda ~2 s en Windows
RUN = uuid.uuid4().hex[:6]
PASSED, FAILED = [], []


def call(method, path, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"null")


def check(name, condition, detail=""):
    (PASSED if condition else FAILED).append(name)
    print(("  OK   " if condition else "  FALLA"), name, "" if condition else f"-> {detail}")


_counter = [0]


def txn(user=f"e2e-{RUN}@correo.com", at=None, **over):
    _counter[0] += 1
    t = {
        "idTxn": f"E2E{RUN}-{_counter[0]}",
        "nombre": "Prueba E2E",
        "cedula": "1012345678",
        "user": user,
        "date": (at or datetime.now()).isoformat(timespec="milliseconds"),
        "value": 50000,
        "paymentMethod": "Tarjeta",
    }
    t.update(over)
    return t


def post(t):
    return call("POST", "/api/transactions", t)


def main():
    if "--clean" in sys.argv:
        from pymongo import MongoClient

        db = MongoClient("mongodb://localhost:27017")["appresso_food"]
        for name in ("transacciones", "anomalias", "logs", "usuarios"):
            db[name].delete_many({})
        print("Colecciones de transacciones limpiadas.")
        return

    day = datetime(2026, 9, 23, 10, 0, 0)  # fecha fija: reproducible y no mezcla con "hoy"
    print(f"Servidor: {BASE}  corrida: {RUN}")

    print("\n[1] Transacción correcta")
    s, b = post(txn(at=day))
    check("1. VALID (201)", s == 201 and b["estado"] == "VALID" and len(b["hash"]) == 64, b)

    print("\n[2-5] Validaciones")
    s, b = post(txn(user=None))
    check("2. null -> REJECTED/NULL_FIELD", s == 422 and b["estado"] == "REJECTED" and b["motivo"] == "NULL_FIELD", b)
    s, b = post(txn(nombre=""))
    check("3. vacío -> REJECTED/EMPTY_FIELD", s == 422 and b["motivo"] == "EMPTY_FIELD", b)
    s, b = post(txn(user="no-es-correo"))
    check("4. email inválido -> INVALID_EMAIL", s == 422 and b["motivo"] == "INVALID_EMAIL", b)
    s, b = post(txn(value=[50000]))
    check("5. tipo incorrecto -> INVALID_TYPE", s == 422 and b["motivo"] == "INVALID_TYPE", b)

    print("\n[6] Número como texto")
    s, b = post(txn(at=day + timedelta(minutes=1), value="50000"))
    check("6. \"50000\" se normaliza -> VALID", s == 201 and b["estado"] == "VALID", b)
    s, b = post(txn(value="abc"))
    check("6b. \"abc\" -> INVALID_VALUE (no se vuelve 0)", s == 422 and b["motivo"] == "INVALID_VALUE", b)

    print("\n[7] ID duplicado")
    original = txn(at=day + timedelta(minutes=2))
    post(original)
    s, b = post(dict(original, date=(day + timedelta(minutes=3)).isoformat()))
    check("7. ID repetido -> 409 DUPLICATE_TRANSACTION", s == 409 and b["motivo"] == "DUPLICATE_TRANSACTION", b)

    print("\n[8] Tres transacciones en 10 s")
    u = f"burst-{RUN}@correo.com"
    t0 = day + timedelta(hours=1)
    states = [post(txn(u, t0 + timedelta(seconds=x)))[1] for x in (1, 4, 8)]
    check("8. 3ª -> SUSPICIOUS / POSSIBLE_FRAUD", [x["estado"] for x in states] == ["VALID", "VALID", "SUSPICIOUS"] and states[2]["motivo"] == "POSSIBLE_FRAUD", states)
    u2 = f"normal-{RUN}@correo.com"
    states = [post(txn(u2, t0 + timedelta(seconds=x)))[1] for x in (1, 5, 12)]
    check("8b. 01/05/12 s -> sin anomalía", [x["estado"] for x in states] == ["VALID"] * 3, states)

    print("\n[9] Usuarios distintos")
    t1 = day + timedelta(hours=2)
    outs = [post(txn(f"u{i}-{RUN}@correo.com", t1 + timedelta(seconds=i)))[1] for i in (1, 2, 3)]
    check("9. ventanas independientes -> todas VALID", all(o["estado"] == "VALID" and o["ventana"]["cantidad"] == 1 for o in outs), outs)

    print("\n[10] Salida de la ventana, el historial se conserva")
    u3 = f"salida-{RUN}@correo.com"
    t2 = day + timedelta(hours=3)
    first = txn(u3, t2)
    post(first)
    post(txn(u3, t2 + timedelta(seconds=3)))
    _, b = post(txn(u3, t2 + timedelta(seconds=14)))
    check("10a. respuesta lista los que salieron", len(b["ventana"]["salieron"]) == 2 and b["ventana"]["cantidad"] == 1, b["ventana"])
    _, win = call("GET", f"/api/window?usuario={u3}")
    check("10b. ventana activa solo tiene 1", len(win["usuarios"][0]["entradas"]) == 1, win)
    _, hist = call("GET", f"/api/transactions?usuario={u3}&limit=20")
    check("10c. el historial sigue teniendo las 3", len([h for h in hist if h["aceptada"]]) == 3, hist)
    _, logs = call("GET", "/api/logs?limit=50&evento=VENTANA_SALE")
    check("10d. hay logs VENTANA_SALE", any(l["id_txn"] == first["idTxn"] for l in logs), logs[:3])

    print("\n[10b] Llegada fuera de orden")
    u4 = f"desorden-{RUN}@correo.com"
    t3 = day + timedelta(hours=5)
    outs = [post(txn(u4, t3 + timedelta(seconds=x)))[1] for x in (10, 1, 2)]
    check("10e. 10:00:10, :01, :02 -> la 3ª SUSPICIOUS con 3 en la ventana", outs[2]["estado"] == "SUSPICIOUS" and outs[2]["ventana"]["cantidad"] == 3, outs[2])
    u5 = f"historial-{RUN}@correo.com"
    t4 = day + timedelta(hours=6)
    outs = [post(txn(u5, t4 + timedelta(seconds=x)))[1] for x in (1, 2, 20, 3)]
    check("10f. :01, :02, :20, :03 -> la 4ª usa el historial y es SUSPICIOUS", outs[3]["estado"] == "SUSPICIOUS" and outs[3]["ventana"]["tardia"] is True, outs[3])
    check("10g. la llegada tardía no aparece como su propia salida", outs[3]["ventana"]["salieron"] == [], outs[3]["ventana"])

    print("\n[11] Hash")
    base = txn(at=day + timedelta(hours=4))
    s, h = call("POST", "/api/transactions/hash", base)
    check("11a. el servidor calcula el hash", s == 200 and len(h["hash"]) == 64, h)
    s, b = post(dict(base, value=99999, hash=h["hash"]))
    check("11b. dato modificado -> HASH_MISMATCH", s == 422 and b["motivo"] == "HASH_MISMATCH", b)
    s, b = post(dict(base, hash=h["hash"]))
    check("11c. hash correcto -> VALID (CLIENTE_VERIFICADO)", s == 201 and b["hash_origen"] == "CLIENTE_VERIFICADO", b)
    s, v = call("GET", f"/api/transactions/{base['idTxn']}/verify")
    check("11d. verificación posterior coincide", s == 200 and v["coincide"] is True, v)
    from pymongo import MongoClient

    MongoClient("mongodb://localhost:27017")["appresso_food"].transacciones.update_one({"id_txn": base["idTxn"], "aceptada": True}, {"$set": {"valor": 1.0}})
    s, v = call("GET", f"/api/transactions/{base['idTxn']}/verify")
    check("11e. dato alterado en la BD -> inconsistencia detectada", s == 200 and v["coincide"] is False, v)

    print("\n[12] Ráfaga tipo bot (hora real)")
    ub = f"bot-{RUN}@correo.com"
    outs = [post(txn(ub))[1] for _ in range(6)]
    check("12. ráfaga de 6 -> SUSPICIOUS desde la 3ª", [o["estado"] for o in outs] == ["VALID", "VALID"] + ["SUSPICIOUS"] * 4, [o["estado"] for o in outs])
    check("12b. nivel sube a ALTO", outs[2]["anomalias"][0]["nivel"] == "MEDIO" and outs[5]["anomalias"][0]["nivel"] == "ALTO", outs[5]["anomalias"])

    print("\n[Extras] JSON malformado, anomalías, estadísticas")
    s, b = call("POST", "/api/transactions", raw=b'{"idTxn": 1, "user": ')
    check("JSON malformado -> 400 MALFORMED_JSON", s == 400 and b["motivo"] == "MALFORMED_JSON", b)
    _, anomalies = call("GET", "/api/anomalies?limit=5")
    check("hay anomalías registradas", len(anomalies) > 0, anomalies)
    s, upd = call("PATCH", f"/api/anomalies/{anomalies[0]['id']}", {"estado": "ABIERTA"})
    check("PATCH cambia el estado de la anomalía", s == 200 and upd["estado"] == "ABIERTA", upd)
    s, _ = call("PATCH", f"/api/anomalies/{anomalies[0]['id']}", {"estado": "XX"})
    check("PATCH con estado inválido -> 400", s == 400)
    s, tl = call("GET", f"/api/anomalies/{anomalies[0]['id']}/timeline")
    check("línea de tiempo de la anomalía", s == 200 and "linea_de_tiempo" in tl, tl)
    s, st = call("GET", "/api/stats")
    check("estadísticas con los periodos del PDF", s == 200 and {"hoy", "semana", "mes"} <= set(st["periodos"]), list(st))

    print(f"\nResultado: {len(PASSED)} OK, {len(FAILED)} con fallas")
    sys.exit(1 if FAILED else 0)


main()
