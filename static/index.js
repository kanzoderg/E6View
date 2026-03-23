
posts_container = document.getElementById('posts');

var search_input = document.getElementById('search_input');
function show_tags() {
    if (search_input) {
        search_input.value = tags.join(' ');
    }
}

function next_page() {
    if (current_page < max_page) {
        url = url_base + '/?page=' + (current_page + 1) + '&tags=' + tags.join(' ');
        if (live) {
            url += '&live=1';
        }
        window.location = url;
    }
}
function prev_page() {
    if (current_page > 1) {
        url = url_base + '/?page=' + (current_page - 1) + '&tags=' + tags.join(' ');
        if (live) {
            url += '&live=1';
        }
        window.location = url;

    }
}

function go_page() {
    page_num = prompt("Page number", "");
    if (isNaN(page_num)) {
        toast("Please enter a valid number");
    }
    if (!page_num) {
        return;
    }
    page_num = Math.min(Math.max(page_num, 1), max_page)
    url = url_base + '/?page=' + page_num + '&tags=' + tags.join(' ');
    if (live) {
        url += '&live=1';
    }
    window.location = url;
}

function searchPosts() {
    var search_input = document.getElementById('search_input');
    if (!search_input) return;
    var search_value = search_input.value;
    url = url_base + '/?page=1&tags=' + search_value;
    if (live) {
        url += '&live=1';
    }
    window.location = url;
}

// debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

suggestions_container = document.getElementById('suggestions');
function auto_complete() {
    if (!search_input) return;
    search_value = search_input.value;
    if (search_value == '') {
        suggestions_container.innerHTML = '';
        suggestions_container.style.display = 'none';
        return;
    }
    // split the search value by space
    value_to_complete = search_value.split(' ').at(-1);
    value_to_complete = value_to_complete.trim().toLowerCase();
    if ((value_to_complete.startsWith('-') && value_to_complete.length < 3) || (!value_to_complete.startsWith('-') && value_to_complete.length < 2)) {
        suggestions_container.innerHTML = '';
        suggestions_container.style.display = 'none';
        return;
    }
    // console.log(search_value, value_to_complete);

    // "/auto_complete?tag=abc"
    fetch(url_base + '/auto_complete?tag=' + value_to_complete)
        .then(response => response.json())
        .then(data => {
            // console.log(data);
            if (data.status == 'ok') {
                suggestions = data.suggestions;
                // console.log(suggestions);
                suggestions_container.innerHTML = '';
                if (suggestions.length == 0) {
                    suggestions_container.style.display = 'none';
                    return;
                }
                show_suggestions(suggestions);
                suggestions_container.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

function show_suggestions(suggestions) {
    suggestions.forEach(function (suggestion) {
        var suggestion_div = document.createElement('div');
        suggestion_div.className = 'suggestion';
        suggestion_div.classList.add('tag');
        suggestion_div.innerHTML = suggestion[0] + "<span class='count'> " + suggestion[1] + "</span>";
        suggestion_div.onclick = function () {
            // add the suggestion to the search input
            is_negative = search_input.value.split(' ').at(-1).startsWith('-');
            if (is_negative) {
                search_input.value = search_input.value.split(' ').slice(0, -1).join(' ') + ' -' + suggestion[0] + ' ';
            }
            else {
                search_input.value = search_input.value.split(' ').slice(0, -1).join(' ') + ' ' + suggestion[0] + ' ';
            }

            suggestions_container.style.display = 'none';
            // search_input.focus();
            searchPosts();
        }
        suggestions_container.appendChild(suggestion_div);
    }
    );
}

function toggle_live() {
    if (live) {
        live = false;
        // In pool mode, we need to manually construct the URL
        if (!search_input) {
            url = url_base + '/?page=1&tags=' + tags.join(' ');
            window.location = url;
        } else {
            searchPosts();
        }
    }
    else {
        live = true;
        // In pool mode, we need to manually construct the URL
        if (!search_input) {
            url = url_base + '/?page=1&tags=' + tags.join(' ') + '&live=1';
            window.location = url;
        } else {
            searchPosts();
        }
    }
}

function download_from_live(tags) {
    if (tags) {
        // warn if search contains certain tags
        var warn_tags = ['male', 'female', 'mammal', 'avian', 'reptile', 'amphibian', 'insect', 'arachnid', 'fish', 'anthro', 'human', 'digital_media_(artwork)', 'traditional_media_(artwork)', 'hi-res'];
        // to string and lowercase
        var lower_tags = tags.toString().toLowerCase();
        for (var i = 0; i < warn_tags.length; i++) {
            if (lower_tags.includes(warn_tags[i])) {
                if (!confirm("Current search may contain VERY LARGE amount of posts. Are you sure you want to continue?")) {
                    return;
                }
                break;
            }
        }

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

// hide autocomplete suggestions when input loses focus
if (search_input) {
    search_input.addEventListener('blur', function () {
        setTimeout(function () {
            suggestions_container.style.display = 'none';
        }, 200);
    });

    // display autocomplete suggestions when input gains focus
    search_input.addEventListener('focus', function () {
        if (suggestions_container.innerHTML != '') {
            debounce_autocomplete();
        }
    });

    debounce_autocomplete = debounce(auto_complete, 500);

    search_input.addEventListener('keyup', function (event) {
        if (event.keyCode == 13) {
            searchPosts();
        }
        else {
            debounce_autocomplete();
        }
    })
}

context_menu = document.getElementById('context_menu');

var selected_post_id = null;

function open_context_menu(event) {
    event.preventDefault();
    var context_menu = document.getElementById('context_menu');
    backdrop = document.getElementById('menu_backdrop');
    backdrop.style.display = 'block';
    context_menu.style.display = 'block';
    context_menu.style.left = Math.min(event.pageX, window.innerWidth - context_menu.offsetWidth - 10) + 'px';
    context_menu.style.top = Math.min(event.pageY, window.innerHeight - context_menu.offsetHeight - 10) + 'px';
    selected_post_id = this.getAttribute('data-id');
    return false;
}

function close_context_menu() {
    var context_menu = document.getElementById('context_menu');
    context_menu.style.display = 'none';
    backdrop = document.getElementById('menu_backdrop');
    backdrop.style.display = 'none';
}

function to_main_tag() {
    if (selected_post_id) {
        close_context_menu();
        url = url_base + '/to_main_tag?id=' + selected_post_id;
        if (live) {
            url += '&live=1';
        }
        window.location = url;
    }
}

function add_to_downloader() {
    if (selected_post_id) {
        fetch(url_base + '/downloader', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ "input": selected_post_id })
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
    close_context_menu();
}

// add event listener to .post elements
posts = document.getElementsByClassName('post');
Array.from(posts).forEach(function (post) {
    post.addEventListener('contextmenu', open_context_menu);
});

show_tags();