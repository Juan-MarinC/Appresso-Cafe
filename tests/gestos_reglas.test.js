// Pruebas del clasificador de gestos con manos sintéticas (sin cámara).
// Ejecutar: node --test tests/gestos_reglas.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const { clasificar, clave, crearTemporizador, muyLejos, rasgos, desdeClave, CLASES } = require("../appresso_food/static/js/gestos-reglas.js");

// Mano derecha de frente, coordenadas de imagen (la y crece hacia abajo). Muñeca en (0, 100).
function mano({ dedos = [], pulgar = "doblado" }) {
    const m = { wrist: { x: 0, y: 100 } };
    const columnas = { index_finger: -15, middle_finger: -5, ring_finger: 5, pinky_finger: 15 };
    for (const [dedo, x] of Object.entries(columnas)) {
        const arriba = dedos.includes(dedo);
        m[dedo + "_mcp"] = { x, y: 60 };
        m[dedo + "_pip"] = { x, y: arriba ? 40 : 45 };
        m[dedo + "_dip"] = { x, y: arriba ? 25 : 55 };
        m[dedo + "_tip"] = { x, y: arriba ? 10 : 65 };  // doblado: la punta vuelve hacia la palma
    }
    m.thumb_cmc = { x: -20, y: 90 };
    m.thumb_mcp = { x: -30, y: 80 };
    const pulgares = {
        doblado: [{ x: -20, y: 72 }, { x: 0, y: 65 }],    // cruzado sobre la palma
        lado: [{ x: -38, y: 70 }, { x: -55, y: 55 }],     // estirado hacia el lado
        arriba: [{ x: -30, y: 50 }, { x: -30, y: 20 }],   // pulgar arriba
    };
    [m.thumb_ip, m.thumb_tip] = pulgares[pulgar];
    return m;
}

const D = ["index_finger", "middle_finger", "ring_finger", "pinky_finger"];

test("1 a 4 dedos eligen el combo con ese número", () => {
    for (let n = 1; n <= 4; n++) {
        assert.deepEqual(clasificar(mano({ dedos: D.slice(0, n) })), { tipo: "combo", numero: n });
    }
});

test("contar con el pulgar estirado también vale; la palma abierta pide ayuda", () => {
    assert.deepEqual(clasificar(mano({ dedos: D.slice(0, 2), pulgar: "lado" })), { tipo: "combo", numero: 2 });
    assert.deepEqual(clasificar(mano({ dedos: D, pulgar: "lado" })), { tipo: "ayuda" });
});

test("pulgar arriba confirma y el puño cancela", () => {
    assert.deepEqual(clasificar(mano({ pulgar: "arriba" })), { tipo: "confirmar" });
    assert.deepEqual(clasificar(mano({})), { tipo: "cancelar" });
});

test("puño con el pulgar hacia el lado no hace nada", () => {
    assert.equal(clasificar(mano({ pulgar: "lado" })), null);
});

test("el gesto debe sostenerse y dispara una sola vez", () => {
    const t = crearTemporizador(1500);
    const g = clave({ tipo: "combo", numero: 2 });
    assert.equal(t(g, 0).disparar, false);
    assert.equal(t(g, 1000).progreso.toFixed(2), "0.67");
    assert.equal(t(g, 1500).disparar, true);
    assert.equal(t(g, 2500).disparar, false);  // sigue sostenido: no repite
});

test("un parpadeo breve no reinicia la cuenta; un cambio sostenido sí", () => {
    const t = crearTemporizador(1500);
    t("combo1", 0);
    t(null, 100);                       // un cuadro sin mano
    assert.equal(t("combo1", 200).progreso.toFixed(2), "0.13");
    t("combo3", 300);
    const r = t("combo3", 600);         // 400 ms después del último combo1: ya es otro gesto
    assert.equal(r.clave, "combo3");
    assert.equal(r.progreso.toFixed(2), "0.00");
});

test("cada gesto puede pedir su propio tiempo de sostén", () => {
    const t = crearTemporizador((k) => (k === "ayuda" ? 3000 : 1500));
    t("ayuda", 0);
    assert.equal(t("ayuda", 1500).disparar, false);
    assert.equal(t("ayuda", 3000).disparar, true);
    t("combo1", 3400);
    assert.equal(t("combo1", 4900).disparar, true);
});

test("una mano muy pequeña en la imagen se considera lejos", () => {
    const m = mano({ dedos: D.slice(0, 2) });     // muñeca→nudillo medio ≈ 40 px
    assert.equal(muyLejos(m, 480), false);        // 40 px de 480: cerca
    assert.equal(muyLejos(m, 720), true);         // 40 px de 720 (< 50,4): lejos
});

// Una mano con la forma de ml5: puntos con nombre y también la lista "keypoints" en orden.
const ORDEN = ["wrist", "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    ...["index_finger", "middle_finger", "ring_finger", "pinky_finger"].flatMap((d) => ["_mcp", "_pip", "_dip", "_tip"].map((s) => d + s))];
function comoMl5(m, { dx = 0, dy = 0, factor = 1, handedness = "Right" } = {}) {
    const r = { handedness, keypoints: [] };
    for (const nombre of ORDEN) {
        const p = { x: m[nombre].x * factor + dx, y: m[nombre].y * factor + dy, name: nombre };
        r[nombre] = p;
        r.keypoints.push(p);
    }
    return r;
}

test("los rasgos son 42 números que no cambian al mover o acercar la mano", () => {
    const base = mano({ dedos: D.slice(0, 2) });
    const a = rasgos(comoMl5(base));
    const b = rasgos(comoMl5(base, { dx: 300, dy: -120, factor: 2.5 }));
    assert.equal(a.length, 42);
    a.forEach((v, i) => assert.ok(Math.abs(v - b[i]) < 1e-9));
});

test("la mano izquierda se refleja para parecerse a la derecha", () => {
    const base = mano({ dedos: D.slice(0, 3) });
    const derecha = rasgos(comoMl5(base));
    const reflejada = { ...base };
    for (const k of Object.keys(base)) reflejada[k] = { x: -base[k].x, y: base[k].y };
    const izquierda = rasgos(comoMl5(reflejada, { handedness: "Left" }));
    izquierda.forEach((v, i) => assert.ok(Math.abs(v - derecha[i]) < 1e-9));
});

test("cada clase de la red se traduce al gesto del kiosko", () => {
    assert.deepEqual(desdeClave("combo3"), { tipo: "combo", numero: 3 });
    assert.deepEqual(desdeClave("confirmar"), { tipo: "confirmar" });
    assert.equal(desdeClave("nada"), null);
    for (const k of CLASES.filter((c) => c !== "nada")) assert.equal(clave(desdeClave(k)), k);
});
