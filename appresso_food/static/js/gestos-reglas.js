// Reglas para leer gestos a partir de los 21 puntos de ml5.handPose. Sin dependencias:
// se usa en el navegador (window.GestosReglas) y en Node para las pruebas.
(function (raiz) {
    const DEDOS = ["index_finger", "middle_finger", "ring_finger", "pinky_finger"];
    const MARGEN = 1.15;  // cuánto más lejos debe quedar la punta para contar el dedo como extendido
    const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

    // Se comparan distancias a la muñeca y no posiciones arriba/abajo, así funciona con la mano inclinada.
    function dedosExtendidos(mano) {
        return DEDOS.filter((d) => dist(mano[d + "_tip"], mano.wrist) > dist(mano[d + "_pip"], mano.wrist) * MARGEN);
    }

    function pulgarExtendido(mano) {
        return dist(mano.thumb_tip, mano.pinky_finger_mcp) > dist(mano.thumb_ip, mano.pinky_finger_mcp) * MARGEN;
    }

    /** Devuelve {tipo: "combo", numero: 1..4} | {tipo: "confirmar"} | {tipo: "cancelar"} | {tipo: "ayuda"} | null. */
    function clasificar(mano) {
        const dedos = dedosExtendidos(mano).length;
        const pulgar = pulgarExtendido(mano);
        const escala = dist(mano.wrist, mano.middle_finger_mcp);  // tamaño de la mano en pantalla
        if (dedos === 0) {
            // Pulgar arriba: la punta queda claramente por encima de los nudillos (y crece hacia abajo).
            if (pulgar && mano.thumb_tip.y < mano.index_finger_mcp.y - escala * 0.3) return { tipo: "confirmar" };
            return pulgar ? null : { tipo: "cancelar" };
        }
        if (dedos === 4 && pulgar) return { tipo: "ayuda" };  // palma abierta, como levantar la mano
        return { tipo: "combo", numero: dedos };
    }

    const clave = (gesto) => (gesto ? gesto.tipo + (gesto.numero || "") : null);

    // Con la mano muy pequeña en la imagen los puntos tiemblan y se confunden los dedos: mejor pedir que se acerque.
    const LEJOS = 0.07;  // muñeca→nudillo medio como fracción del alto del video; ~1,5 m con una cámara de portátil
    const muyLejos = (mano, altoVideo) => dist(mano.wrist, mano.middle_finger_mcp) < altoVideo * LEJOS;

    /**
     * Un gesto solo cuenta si se sostiene `msNecesarios` (un número, o una función clave -> ms para
     * pedir más tiempo a ciertos gestos). Parpadeos de otro gesto más cortos que
     * `msTolerancia` (ruido entre cuadros) no reinician la cuenta. Dispara una sola vez por gesto:
     * para repetirlo hay que soltarlo.
     */
    function crearTemporizador(msNecesarios, msTolerancia = 250) {
        let actual = null, desde = 0, visto = 0, disparado = false;
        return function actualizar(nueva, ahora) {
            if (nueva === actual) {
                visto = ahora;
            } else if (actual === null || ahora - visto > msTolerancia) {
                actual = nueva; desde = ahora; visto = ahora; disparado = false;
            }
            if (actual === null) return { clave: null, progreso: 0, disparar: false };
            const ms = typeof msNecesarios === "function" ? msNecesarios(actual) : msNecesarios;
            const progreso = Math.min(1, (ahora - desde) / ms);
            const disparar = progreso >= 1 && !disparado;
            if (disparar) disparado = true;
            return { clave: actual, progreso, disparar };
        };
    }

    const api = { clasificar, clave, crearTemporizador, muyLejos };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else raiz.GestosReglas = api;
})(typeof window !== "undefined" ? window : globalThis);
