var search_input = document.getElementById('search_input');

function searchPools() {
    var search_value = search_input.value;
    url = url_base + '/pools?q=' + search_value;
    window.location = url;
}

function next_page() {
    var search_value = search_input.value;
    if (current_page < max_page) {
        url = url_base + '/pools?page=' + (current_page + 1) + '&q=' + search_value;
        window.location = url;
    }
}

function prev_page() {
    var search_value = search_input.value;
    if (current_page > 1) {
        url = url_base + '/pools?page=' + (current_page - 1) + '&q=' + search_value;
        window.location = url;
    }
}
