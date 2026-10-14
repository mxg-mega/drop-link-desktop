document.getElementById('uploadForm').addEventListener('submit', function(e) {
    e.preventDefault();

    const form = e.target;
    const fileInput = document.getElementById('fileInput');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const uploadBtn = document.getElementById('uploadBtn');

    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    const xhr = new XMLHttpRequest();

    // Show progress bar
    progressContainer.style.display = 'block';
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';

    // Update progress
    xhr.upload.addEventListener('progress', function(e) {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            progressBar.style.width = percent + '%';
            progressText.textContent = percent + '%';
        }
    });

    // When finished
    xhr.addEventListener('load', function() {
        if (xhr.status === 200 || xhr.status === 303) {
            // Redirect to show success message
            window.location.href = '/?success=File uploaded successfully!';
        } else {
            alert('Upload failed');
            resetUploadUI();
        }
    });

    xhr.addEventListener('error', function() {
        alert('Upload failed');
        resetUploadUI();
    });

    xhr.open('POST', '/upload-web');
    xhr.send(formData);

    function resetUploadUI() {
        progressContainer.style.display = 'none';
        progressBar.style.width = '0%';
        progressText.textContent = '0%';
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload';
    }
});