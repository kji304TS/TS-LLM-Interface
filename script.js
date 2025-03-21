// Function to handle form submission
function submitSelection(event) {
    event.preventDefault(); // Prevents page reload

    // Get user inputs
    const script = document.getElementById("scriptSelect").value;
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;

    if (!script || !startDate || !endDate) {
        alert("Please fill in all fields.");
        return;
    }

    // Send the form data to the backend API
    fetch("https://intercom-llm-buddy.onrender.com/run-script/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script_name: script, start_date: startDate, end_date: endDate })
    })
    .then(response => response.json())
    .then(data => {
        alert(`Script Output: ${data.output}`); // Show backend response in alert
    })
    .catch(error => {
        alert(`Error: ${error.message}`);
        console.error("API call failed:", error);
    });
}

// Attach the function to the form submit event
document.getElementById("scriptForm").addEventListener("submit", submitSelection);



