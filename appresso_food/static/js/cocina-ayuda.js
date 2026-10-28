// Cocina: muestra los avisos de ayuda que llegan desde /gestos y permite atenderlos.
(function () {
    const CADA_MS = 3000;
    const aviso = document.getElementById("aviso-ayuda");
    const hace = document.getElementById("aviso-ayuda-hace");
    const titulo = document.title;
    let pendiente = null;

    async function revisar() {
        let avisos;
        try {
            avisos = await (await fetch("/api/ayuda")).json();
            pendiente = avisos[0] || null;
        } catch (error) {
            return;  // sin conexión: se reintenta en la siguiente vuelta
        }
        aviso.hidden = !pendiente;
        document.title = pendiente ? "🖐️ Ayuda · " + titulo : titulo;
        if (pendiente) {
            const otros = avisos.length > 1 ? ` · ${avisos.length - 1} aviso(s) más` : "";
            hace.textContent = `Hace ${pendiente.hace_segundos} s${otros}`;
        }
    }

    document.getElementById("aviso-ayuda-ok").addEventListener("click", async () => {
        if (!pendiente) return;
        await fetch(`/api/ayuda/${pendiente.id}/atender`, { method: "POST" });
        revisar();
    });

    revisar();
    setInterval(revisar, CADA_MS);
})();
