// Dicas (ⓘ): abre e fecha o texto ao tocar no símbolo, para telas de toque.
// Em computador o texto aparece ao passar o mouse, via CSS.
document.addEventListener('click', function (evento) {
    const botao = evento.target.closest('.dica-botao');

    document.querySelectorAll('.dica.aberta').forEach(function (dica) {
        if (!botao || dica !== botao.parentElement) {
            dica.classList.remove('aberta');
        }
    });

    if (botao) {
        botao.parentElement.classList.toggle('aberta');
    }
});
