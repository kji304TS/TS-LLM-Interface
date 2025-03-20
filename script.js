function submitSelection() {
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const script = document.getElementById("scriptSelect").value;

    if (!startDate || !endDate || !script) {
        alert("Please fill in all fields.");
        return;
    }

    fetch("https://your-app.onrender.com/run-script/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script_name: script, start_date: startDate, end_date: endDate }),
    })
    .then(response => response.json())
    .then(data => alert(`Script Output: ${data.output}`))
    .catch(error => alert(`Error: ${error}`));
}
