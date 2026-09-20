/* =====================================
   PDF MERGER
===================================== */

const fileInput =
    document.getElementById("fileInput");

const dropArea =
    document.getElementById("dropArea");

const fileSection =
    document.getElementById("fileSection");

const fileList =
    document.getElementById("fileList");

const mergeButton =
    document.getElementById("mergeButton");

const clearButton =
    document.getElementById("clearButton");

const status =
    document.getElementById("status");


let selectedFiles = [];


/* =====================================
   FILE INPUT
===================================== */

fileInput.addEventListener("change", function () {

    addFiles(Array.from(this.files));

});


/* =====================================
   ADD FILES
===================================== */

function addFiles(files) {

    const pdfFiles = files.filter(function(file) {

        return file.type === "application/pdf";

    });


    selectedFiles.push(...pdfFiles);


    renderFiles();

}


/* =====================================
   DRAG & DROP
===================================== */

dropArea.addEventListener("dragover", function(event) {

    event.preventDefault();

    dropArea.classList.add("dragover");

});


dropArea.addEventListener("dragleave", function() {

    dropArea.classList.remove("dragover");

});


dropArea.addEventListener("drop", function(event) {

    event.preventDefault();

    dropArea.classList.remove("dragover");

    const files =
        Array.from(event.dataTransfer.files);

    addFiles(files);

});


/* =====================================
   RENDER FILES
===================================== */

function renderFiles() {

    fileList.innerHTML = "";


    if (selectedFiles.length === 0) {

        fileSection.style.display = "none";

        return;

    }


    fileSection.style.display = "block";


    selectedFiles.forEach(function(file, index) {

        const item =
            document.createElement("div");

        item.className = "file-item";


        item.innerHTML = `

            <div class="file-number">
                ${index + 1}
            </div>

            <div class="file-details">

                <div class="file-name">
                    ${escapeHTML(file.name)}
                </div>

                <div class="file-size">
                    ${formatFileSize(file.size)}
                </div>

            </div>

            <button
                class="remove-file"
                onclick="removeFile(${index})"
            >
                ✕
            </button>

        `;


        fileList.appendChild(item);

    });

}


/* =====================================
   REMOVE FILE
===================================== */

function removeFile(index) {

    selectedFiles.splice(index, 1);

    renderFiles();

}


/* =====================================
   CLEAR ALL
===================================== */

clearButton.addEventListener("click", function() {

    selectedFiles = [];

    fileInput.value = "";

    status.textContent = "";

    renderFiles();

});


/* =====================================
   MERGE PDFs
===================================== */

mergeButton.addEventListener("click", async function() {

    if (selectedFiles.length < 2) {

        status.textContent =
            "⚠️ Please select at least 2 PDF files.";

        return;

    }


    try {

        mergeButton.disabled = true;

        status.textContent =
            "⏳ Merging your PDFs...";


        const mergedPdf =
            await PDFLib.PDFDocument.create();


        for (const file of selectedFiles) {

            const fileBytes =
                await file.arrayBuffer();


            const pdf =
                await PDFLib.PDFDocument.load(fileBytes);


            const pages =
                await mergedPdf.copyPages(
                    pdf,
                    pdf.getPageIndices()
                );


            pages.forEach(function(page) {

                mergedPdf.addPage(page);

            });

        }


        const mergedBytes =
            await mergedPdf.save();


        downloadPDF(
            mergedBytes,
            "ToolBox-Merged.pdf"
        );


        status.textContent =
            "✅ PDFs merged successfully!";


    } catch (error) {

        console.error(error);

        status.textContent =
            "❌ Something went wrong while merging the PDFs.";

    }


    mergeButton.disabled = false;

});


/* =====================================
   DOWNLOAD
===================================== */

function downloadPDF(bytes, filename) {

    const blob =
        new Blob(
            [bytes],
            { type: "application/pdf" }
        );


    const url =
        URL.createObjectURL(blob);


    const link =
        document.createElement("a");


    link.href = url;

    link.download = filename;

    document.body.appendChild(link);

    link.click();

    link.remove();

    URL.revokeObjectURL(url);

}


/* =====================================
   FILE SIZE
===================================== */

function formatFileSize(bytes) {

    if (bytes === 0) {
        return "0 Bytes";
    }


    const units = [
        "Bytes",
        "KB",
        "MB",
        "GB"
    ];


    const i =
        Math.floor(
            Math.log(bytes) /
            Math.log(1024)
        );


    return (
        parseFloat(
            (bytes /
            Math.pow(1024, i))
            .toFixed(2)
        )
        + " "
        + units[i]
    );

}


/* =====================================
   BASIC HTML ESCAPING
===================================== */

function escapeHTML(text) {

    const div =
        document.createElement("div");

    div.textContent = text;

    return div.innerHTML;

}