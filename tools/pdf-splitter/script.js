/* =====================================
   PDF SPLITTER
===================================== */

const fileInput =
    document.getElementById("fileInput");

const dropArea =
    document.getElementById("dropArea");

const pdfSection =
    document.getElementById("pdfSection");

const fileName =
    document.getElementById("fileName");

const fileDetails =
    document.getElementById("fileDetails");

const pageRange =
    document.getElementById("pageRange");

const splitButton =
    document.getElementById("splitButton");

const removeButton =
    document.getElementById("removeButton");

const status =
    document.getElementById("status");


let selectedFile = null;

let pdfDocument = null;


/* =====================================
   FILE INPUT
===================================== */

fileInput.addEventListener(
    "change",
    function () {

        if (this.files.length > 0) {

            loadPDF(this.files[0]);

        }

    }
);


/* =====================================
   DRAG OVER
===================================== */

dropArea.addEventListener(
    "dragover",
    function (event) {

        event.preventDefault();

        dropArea.classList.add("dragover");

    }
);


/* =====================================
   DRAG LEAVE
===================================== */

dropArea.addEventListener(
    "dragleave",
    function () {

        dropArea.classList.remove("dragover");

    }
);


/* =====================================
   DROP
===================================== */

dropArea.addEventListener(
    "drop",
    function (event) {

        event.preventDefault();

        dropArea.classList.remove("dragover");

        const file =
            event.dataTransfer.files[0];

        if (file) {

            loadPDF(file);

        }

    }
);


/* =====================================
   LOAD PDF
===================================== */

async function loadPDF(file) {

    if (file.type !== "application/pdf") {

        status.textContent =
            "⚠️ Please select a valid PDF file.";

        return;

    }


    try {

        status.textContent =
            "⏳ Reading PDF...";


        selectedFile = file;


        const bytes =
            await file.arrayBuffer();


        pdfDocument =
            await PDFLib.PDFDocument.load(bytes);


        const pageCount =
            pdfDocument.getPageCount();


        fileName.textContent =
            file.name;


        fileDetails.textContent =
            `${pageCount} page${pageCount !== 1 ? "s" : ""} • ${formatFileSize(file.size)}`;


        pdfSection.style.display =
            "block";


        status.textContent = "";


    } catch (error) {

        console.error(error);

        status.textContent =
            "❌ Unable to read this PDF.";

        selectedFile = null;

        pdfDocument = null;

    }

}


/* =====================================
   REMOVE PDF
===================================== */

removeButton.addEventListener(
    "click",
    function () {

        selectedFile = null;

        pdfDocument = null;

        fileInput.value = "";

        pageRange.value = "";

        pdfSection.style.display =
            "none";

        status.textContent = "";

    }
);


/* =====================================
   SPLIT PDF
===================================== */

splitButton.addEventListener(
    "click",
    async function () {

        if (!pdfDocument) {

            status.textContent =
                "⚠️ Please upload a PDF first.";

            return;

        }


        const rangeText =
            pageRange.value.trim();


        if (!rangeText) {

            status.textContent =
                "⚠️ Enter the pages you want to extract.";

            return;

        }


        try {

            splitButton.disabled = true;

            status.textContent =
                "⏳ Extracting pages...";


            const pageNumbers =
                parsePageRange(
                    rangeText,
                    pdfDocument.getPageCount()
                );


            if (pageNumbers.length === 0) {

                throw new Error(
                    "No valid pages selected."
                );

            }


            const newPdf =
                await PDFLib.PDFDocument.create();


            const pages =
                await newPdf.copyPages(
                    pdfDocument,
                    pageNumbers.map(
                        page => page - 1
                    )
                );


            pages.forEach(function(page) {

                newPdf.addPage(page);

            });


            const newBytes =
                await newPdf.save();


            const originalName =
                selectedFile.name
                    .replace(/\.pdf$/i, "");


            const outputName =
                `${originalName}-extracted.pdf`;


            downloadPDF(
                newBytes,
                outputName
            );


            status.textContent =
                `✅ ${pageNumbers.length} page${pageNumbers.length !== 1 ? "s" : ""} extracted successfully!`;


        } catch (error) {

            console.error(error);

            status.textContent =
                "❌ " + error.message;

        }


        splitButton.disabled = false;

    }
);


/* =====================================
   PARSE PAGE RANGE
===================================== */

function parsePageRange(text, maxPages) {

    const pages = new Set();


    const parts =
        text.split(",");


    for (let part of parts) {

        part = part.trim();


        if (!part) {
            continue;
        }


        /* RANGE */

        if (part.includes("-")) {

            const range =
                part.split("-");


            if (range.length !== 2) {
                continue;
            }


            let start =
                parseInt(range[0].trim());

            let end =
                parseInt(range[1].trim());


            if (
                isNaN(start) ||
                isNaN(end)
            ) {

                continue;

            }


            if (start > end) {

                [start, end] =
                    [end, start];

            }


            start =
                Math.max(1, start);

            end =
                Math.min(maxPages, end);


            for (
                let i = start;
                i <= end;
                i++
            ) {

                pages.add(i);

            }

        }

        /* SINGLE PAGE */

        else {

            const page =
                parseInt(part);


            if (
                !isNaN(page) &&
                page >= 1 &&
                page <= maxPages
            ) {

                pages.add(page);

            }

        }

    }


    return Array.from(pages)
        .sort(function(a, b) {
            return a - b;
        });

}


/* =====================================
   DOWNLOAD PDF
===================================== */

function downloadPDF(bytes, filename) {

    const blob =
        new Blob(
            [bytes],
            {
                type: "application/pdf"
            }
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


    const index =
        Math.floor(
            Math.log(bytes) /
            Math.log(1024)
        );


    return (
        parseFloat(
            (
                bytes /
                Math.pow(1024, index)
            ).toFixed(2)
        )
        +
        " " +
        units[index]
    );

}