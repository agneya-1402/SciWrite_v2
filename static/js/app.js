document.addEventListener('DOMContentLoaded', () => {
    
    // --- Accordion on Results Page ---
    const accordionItems = document.querySelectorAll('.accordion-item');
    if (accordionItems.length > 0) {
        accordionItems.forEach(item => {
            const header = item.querySelector('.accordion-header');
            header.addEventListener('click', () => {
                // Close other items
                accordionItems.forEach(otherItem => {
                    if (otherItem !== item && otherItem.classList.contains('active')) {
                        otherItem.classList.remove('active');
                        otherItem.querySelector('.accordion-content').style.maxHeight = null;
                    }
                });

                // Toggle current item
                item.classList.toggle('active');
                const content = item.querySelector('.accordion-content');
                if (item.classList.contains('active')) {
                    content.style.maxHeight = content.scrollHeight + "px";
                } else {
                    content.style.maxHeight = null;
                }
            });
        });
    }

    // --- Generate Page Logic ---
    const generateForm = document.getElementById('generate-form');
    if (generateForm) {
        // Author table
        const authorsTable = document.getElementById('authors-table');
        const addAuthorBtn = document.getElementById('add-author-btn');
        let authorIndex = 0;

        const addAuthorRow = () => {
            const row = document.createElement('div');
            row.className = 'table-row';
            row.innerHTML = `
                <input type="text" name="authors[${authorIndex}][name]" placeholder="Author Name" required>
                <input type="text" name="authors[${authorIndex}][affiliation]" placeholder="Affiliation" required>
                <button type="button" class="remove-row-btn" title="Remove Author">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>
                </button>
            `;
            authorsTable.appendChild(row);
            authorIndex++;
        };

        addAuthorBtn.addEventListener('click', addAuthorRow);
        authorsTable.addEventListener('click', (e) => {
            if (e.target.closest('.remove-row-btn')) {
                e.target.closest('.table-row').remove();
            }
        });
        addAuthorRow(); // Start with one author row

        // Chart descriptions table
        const chartsTable = document.getElementById('charts-table');
        const addChartBtn = document.getElementById('add-chart-btn');
        let chartIndex = 0;

        const addChartRow = () => {
            const row = document.createElement('div');
            row.className = 'table-row';
            row.innerHTML = `
                <input type="text" name="chart_captions[${chartIndex}]" placeholder="Describe the chart to generate (e.g., A bar chart of user engagement)" required>
                <button type="button" class="remove-row-btn" title="Remove Chart">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>
                </button>
            `;
            chartsTable.appendChild(row);
            chartIndex++;
        };
        addChartBtn.addEventListener('click', addChartRow);
        chartsTable.addEventListener('click', (e) => {
            if (e.target.closest('.remove-row-btn')) {
                e.target.closest('.table-row').remove();
            }
        });

        // Drag and drop file upload
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('figure-upload');
        const filePreviews = document.getElementById('file-previews');
        const uploadedFiles = new DataTransfer();

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            const files = e.dataTransfer.files;
            handleFiles(files);
        });
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });

        const handleFiles = (files) => {
            for (const file of files) {
                if (file.type.startsWith('image/')) {
                    uploadedFiles.items.add(file);
                    createFilePreview(file);
                }
            }
            fileInput.files = uploadedFiles.files;
        };

        let figureCaptionIndex = 0;
        const createFilePreview = (file) => {
            const previewItem = document.createElement('div');
            previewItem.className = 'file-preview-item';
            previewItem.innerHTML = `
                <span>${file.name}</span>
                <input type="text" name="figure_captions[${figureCaptionIndex}]" placeholder="Enter caption for this figure" required>
                <button type="button" class="remove-row-btn" title="Remove Figure">&times;</button>
            `;
            filePreviews.appendChild(previewItem);
            figureCaptionIndex++;

            previewItem.querySelector('.remove-row-btn').addEventListener('click', () => {
                previewItem.remove();
                // This is a simplified removal. A more robust implementation
                // would modify the `uploadedFiles` DataTransfer object.
            });
        };

        // Form submission and progress handling
        const progressOverlay = document.getElementById('progress-overlay');
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        const timerSpan = document.getElementById('timer');
        let timerInterval;

        generateForm.addEventListener('submit', (e) => {
            e.preventDefault();
            progressOverlay.classList.remove('hidden');
            
            let seconds = 0;
            timerInterval = setInterval(() => {
                seconds++;
                const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
                const secs = (seconds % 60).toString().padStart(2, '0');
                timerSpan.textContent = `${mins}:${secs}`;
            }, 1000);

            const formData = new FormData(generateForm);
            
            // Append files correctly
            for (const file of uploadedFiles.files) {
                formData.append('figures', file);
            }

            fetch('/api/generate', {
                method: 'POST',
                body: formData,
            }).then(response => {
                 const reader = response.body.getReader();
                 const decoder = new TextDecoder();

                 function push() {
                     reader.read().then(({ done, value }) => {
                         if (done) {
                             console.log('Stream complete');
                             return;
                         }
                         const chunk = decoder.decode(value, {stream: true});
                         
                         // Process server-sent events
                         const lines = chunk.split('\n\n');
                         lines.forEach(line => {
                             if (line.startsWith('event: progress')) {
                                 const data = JSON.parse(line.substring(line.indexOf('{')));
                                 progressBar.style.width = `${data.progress}%`;
                                 progressText.textContent = data.status;
                             } else if (line.startsWith('event: status')) {
                                 const data = line.substring(line.indexOf('data: ') + 6);
                                 progressText.textContent = data;
                             } else if (line.startsWith('event: complete')) {
                                 clearInterval(timerInterval);
                                 // Redirect directly to /results to ensure session is picked up
                                 window.location.href = '/results';
                             }
                         });
                         push();
                     });
                 }
                 push();
            }).catch(error => {
                console.error('Error:', error);
                progressText.textContent = `Error: ${error.message}. Please check console.`;
                clearInterval(timerInterval);
            });
        });
    }
});
