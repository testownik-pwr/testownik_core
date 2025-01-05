document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('file-input');
    const linkInput = document.getElementById('link-input');
    const textInput = document.getElementById('text-input');
    const fileBox = document.getElementById('file-box');
    let uploadType = 'link';

    fileBox.addEventListener('click', () => fileInput.click());

    document.querySelectorAll('.btn-group .btn').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.btn-group .btn').forEach(b => b.classList.remove('active'));
            button.classList.add('active');
            uploadType = button.dataset.uploadType;
            document.getElementById('file').style.display = uploadType === 'file' ? 'block' : 'none';
            document.getElementById('link').style.display = uploadType === 'link' ? 'block' : 'none';
            document.getElementById('text').style.display = uploadType === 'json' ? 'block' : 'none';
        });
    });

    fileInput.addEventListener('change', handleFileSelect);
    fileBox.addEventListener('dragover', handleDragOver);
    fileBox.addEventListener('dragleave', handleDragLeave);
    fileBox.addEventListener('drop', handleFileDrop);

    document.getElementById('import-button').addEventListener('click', () => {
        importQuiz((data) => {
            fetch('/quizzes/import/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(data)
            }).then(response => {
                if (response.ok) {
                    response.json().then(data => {
                        window.location.href = `/quizzes/${data.id}/`;
                    });
                } else {
                    response.json().then(data => {
                        const error = document.getElementById('import-error');
                        error.textContent = data.error || 'Wystąpił błąd podczas importowania quizu. Odśwież stronę i spróbuj ponownie.';
                        error.classList.remove('d-none');
                    });
                }
            });
        });
    });

    function handleFileSelect(evt) {
        const file = evt.target.files[0];
        const name = document.getElementById('file-name');
        if (file) {
            name.textContent = file.name;
            name.classList.remove('d-none');
        } else {
            name.classList.add('d-none');
        }
        handleDragLeave();
    }

    function handleFileDrop(evt) {
        evt.preventDefault();
        evt.stopPropagation();
        const file = evt.dataTransfer.files[0];
        if (file) {
            if (file.type !== 'application/json') {
                showError('file-help', 'Wybrany plik nie jest plikiem JSON.');
                return;
            }
            fileInput.files = evt.dataTransfer.files;
            handleFileSelect({target: {files: [file]}});
            hideError('file-help');
        }
    }

    function handleDragOver(evt) {
        evt.preventDefault();
        evt.stopPropagation();
        if (evt.dataTransfer.items && evt.dataTransfer.items.length === 1 && evt.dataTransfer.items[0].kind === 'file' && evt.dataTransfer.items[0].type === 'application/json') {
            evt.dataTransfer.dropEffect = 'copy';
            fileBox.classList.add('border-primary');
        } else {
            evt.dataTransfer.dropEffect = 'none';
        }
    }

    function handleDragLeave(evt) {
        if (evt) {
            evt.preventDefault();
            evt.stopPropagation();
        }
        fileBox.classList.remove('border-primary');
    }

    function importQuiz(callback) {
        let data = {type: uploadType, data: null};
        if (uploadType === 'file') {
            const file = fileInput.files[0];
            if (!file) return showError('file-help', 'Wybierz plik z quizem.');
            const reader = new FileReader();
            reader.onload = (e) => {
                data.type = 'json';
                data.data = JSON.parse(e.target.result);
                callback(data);
            };
            reader.onerror = () => showError('file-help', 'Wystąpił błąd podczas wczytywania pliku.');
            reader.readAsText(file);
        } else if (uploadType === 'link') {
            if (!linkInput.value) return showError('link-help', 'Wklej link do quizu.');
            if (!validateLink(linkInput.value)) return showError('link-help', 'Link jest niepoprawny.');
            data.data = linkInput.value;
            callback(data);
        } else if (uploadType === 'json') {
            if (!textInput.value) return showError('text-help', 'Wklej quiz w formie tekstu.');
            if (!validateJSON(textInput.value)) return showError('text-help', 'Quiz jest niepoprawny. Upewnij się, że jest w formacie JSON.');
            data.data = JSON.parse(textInput.value);
            callback(data);
        }
    }

    function showError(id, message) {
        const help = document.getElementById(id);
        help.textContent = message;
        help.classList.remove('d-none');
        help.classList.add('text-danger');
    }

    function hideError(id) {
        const help = document.getElementById(id);
        help.textContent = '';
        help.classList.add('d-none');
        help.classList.remove('text-danger');
    }

    function validateLink(link) {
        try {
            new URL(link);
            return true;
        } catch {
            return false;
        }
    }

    function validateJSON(json) {
        try {
            JSON.parse(json);
            return true;
        } catch {
            return false;
        }
    }
});