const $ = selector => document.querySelector(selector);

$("#run").onclick = () => {
    const match = $("#input").value.trim().match(/^(-?\d+(?:\.\d+)?)\s*(c|f|k)$/i);
    if (!match) {
        $("#out").textContent = "Enter a value with a unit, such as 100 C.";
        return;
    }
    const value = Number(match[1]);
    const unit = match[2].toLowerCase();
    const celsius = unit === "c" ? value : unit === "f" ? (value - 32) * 5 / 9 : value - 273.15;
    $("#out").textContent = `${celsius.toFixed(2)} °C | ${(celsius * 9 / 5 + 32).toFixed(2)} °F | ${(celsius + 273.15).toFixed(2)} K`;
};
