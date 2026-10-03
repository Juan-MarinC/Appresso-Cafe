// Menú desplegable en pantallas pequeñas
(function () {
    const boton = document.getElementById("menu-movil");
    const nav = document.getElementById("nav");
    if (!boton || !nav) return;
    boton.addEventListener("click", function () {
        const abierto = nav.classList.toggle("abierto");
        boton.setAttribute("aria-expanded", String(abierto));
    });
})();
