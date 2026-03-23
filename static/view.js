media_container = document.getElementById('media_container');

function download_from_live(tags) {
    if (tags) {
        fetch(url_base + '/downloader', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ "input": tags })
        }).then(response => {
            if (response.ok) {
                return response.json();
            } else {
                throw new Error('Network response was not ok');
            }
        }).then(data => {
            toast(data.message);
        });
    }
}

function show_prev_btn() {
    prev_btn = document.getElementById('prev_btn');
    prev_btn.style.opacity = '0.5';
    setTimeout(() => {
        prev_btn.style.opacity = '0';
    }, 1000);
}

function show_next_btn() {
    next_btn = document.getElementById('next_btn');
    next_btn.style.opacity = '0.5';
    setTimeout(() => {
        next_btn.style.opacity = '0';
    }, 1000);
}
