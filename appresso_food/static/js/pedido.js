// Resumen en vivo del formulario de pedido. Solo muestra: el servidor recalcula todo al enviar.
(function () {
    const form = document.getElementById("order-form");
    if (!form) return;
    const cards = [...form.querySelectorAll(".menu-card")];
    const lista = document.getElementById("resumen-lista");
    const vacio = document.getElementById("resumen-vacio");
    const total = document.getElementById("resumen-total");
    const enviar = document.getElementById("resumen-enviar");
    const barra = document.getElementById("barra-pedido");
    const barraTexto = document.getElementById("barra-pedido-texto");

    const money = (n) => "$" + n.toLocaleString("es-CO", { maximumFractionDigits: 0 });
    const cantidad = (input) => Math.max(0, parseInt(input.value, 10) || 0);

    function actualizar() {
        let unidades = 0, suma = 0;
        lista.replaceChildren();
        cards.forEach((card) => {
            const n = cantidad(card.querySelector('input[name="quantity"]'));
            card.classList.toggle("elegido", n > 0);
            if (!n) return;
            const subtotal = n * Number(card.dataset.precio);
            unidades += n;
            suma += subtotal;
            const li = document.createElement("li");
            const nombre = document.createElement("span");
            const valor = document.createElement("strong");
            nombre.textContent = `${n} × ${card.dataset.nombre}`;
            valor.textContent = money(subtotal);
            li.append(nombre, valor);
            lista.append(li);
        });
        vacio.hidden = unidades > 0;
        total.textContent = money(suma);
        enviar.disabled = unidades === 0;
        barra.hidden = unidades === 0;
        barraTexto.textContent = `${unidades} ${unidades === 1 ? "producto" : "productos"} · ${money(suma)}`;
    }

    form.addEventListener("click", (event) => {
        const boton = event.target.closest("[data-paso]");
        if (!boton) return;
        const input = boton.parentElement.querySelector('input[name="quantity"]');
        input.value = Math.max(0, cantidad(input) + Number(boton.dataset.paso));
        actualizar();
    });
    form.addEventListener("input", actualizar);

    // Filtro por categoría: ocultar no quita la tarjeta del formulario, sus cantidades se siguen enviando
    const chips = [...form.querySelectorAll(".chip-cat")];
    chips.forEach((chip) => chip.addEventListener("click", () => {
        chips.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
        cards.forEach((card) => {
            card.hidden = Boolean(chip.dataset.categoria) && card.dataset.categoria !== chip.dataset.categoria;
        });
    }));

    actualizar();
})();
