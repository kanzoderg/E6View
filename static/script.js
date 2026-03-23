function toast(message, level = "info") {
    const toastElement = document.getElementById('toast');
    if (toastElement) {
        toastElement.textContent = message;
        toastElement.style.display = 'block';
        toastElement.style.opacity = '0.8';
        setTimeout(() => {
            toastElement.style.opacity = '0';
            setTimeout(() => {
                toastElement.style.display = 'none';
            }, 300);
        }, 2000);
    }
    console.log(message);
}

function toggle_menu() {
    menu = document.getElementById('menu');
    backdrop = document.getElementById('menu_backdrop');
    if (menu.style.display == 'block') {
        menu.style.display = 'none';
        backdrop.style.display = 'none';
    } else {
        menu.style.display = 'block';
        backdrop.style.display = 'block';
    }
}

function hide_menu() {
    menu = document.getElementById('menu');
    menu.style.display = 'none';
    context_menu = document.getElementById('context_menu');
    if (context_menu) context_menu.style.display = 'none';
    backdrop = document.getElementById('menu_backdrop');
    backdrop.style.display = 'none';
}

function show_menu() {
    menu = document.getElementById('menu');
    menu.style.display = 'block';
    backdrop = document.getElementById('menu_backdrop');
    backdrop.style.display = 'block';
}

function toggle_fullscreen() {
    // 如果在 iframe 中，向父窗口发送消息
    if (window.parent !== window) {
        window.parent.postMessage({ action: 'toggleFullscreen' }, '*');
        hide_menu();
        return;
    }

    // 独立页面的原始逻辑
    if (!document.fullscreenElement) {
        document.body.requestFullscreen().catch(err => {
            toast(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
        });
    } else {
        document.exitFullscreen();
    }
    hide_menu();
}