const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..");

function runTool(relativePath, values) {
    const elements = new Map(Object.entries(values).map(([id, value]) => [
        `#${id}`,
        { value, textContent: "", onclick: null }
    ]));
    const context = {
        document: { querySelector: selector => elements.get(selector) },
        console
    };
    vm.runInNewContext(fs.readFileSync(path.join(root, relativePath), "utf8"), context);
    elements.get("#run").onclick();
    return elements.get("#out").textContent;
}

const percentage = runTool("tools/percentage-change/script.js", { a: "100", b: "125", run: "", out: "" });
assert.strictEqual(percentage, "25.00%");

const temperature = runTool("tools/unit-temperature/script.js", { input: "32 F", run: "", out: "" });
assert.match(temperature, /^0\.00 °C \| 32\.00 °F \| 273\.15 K$/);

const csv = runTool("tools/csv-to-json/script.js", { input: "name,city\nAda,London", run: "", out: "" });
assert.deepStrictEqual(JSON.parse(csv), [{ name: "Ada", city: "London" }]);

console.log("Representative calculator, converter, and file-data checks passed.");
