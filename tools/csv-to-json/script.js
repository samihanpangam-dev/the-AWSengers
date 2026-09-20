const $ = selector => document.querySelector(selector);

function parseCsvLine(line) {
    const cells = [];
    let cell = "";
    let quoted = false;
    for (let index = 0; index < line.length; index += 1) {
        const character = line[index];
        if (character === '"' && line[index + 1] === '"') {
            cell += '"';
            index += 1;
        } else if (character === '"') {
            quoted = !quoted;
        } else if (character === "," && !quoted) {
            cells.push(cell.trim());
            cell = "";
        } else {
            cell += character;
        }
    }
    cells.push(cell.trim());
    return cells;
}

$("#run").onclick = () => {
    const lines = $("#input").value.split(/\r?\n/).filter(line => line.trim());
    if (lines.length < 2) {
        $("#out").textContent = "Add a header row and at least one data row.";
        return;
    }
    const headers = parseCsvLine(lines[0]);
    const rows = lines.slice(1).map(line => {
        const values = parseCsvLine(line);
        return Object.fromEntries(headers.map((header, index) => [
            header || `column${index + 1}`,
            values[index] || ""
        ]));
    });
    $("#out").textContent = JSON.stringify(rows, null, 2);
};
