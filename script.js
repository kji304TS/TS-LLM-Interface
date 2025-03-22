// Function to handle form submission
function submitSelection(event) {
    event.preventDefault(); // Prevent form reload

    const script = document.getElementById("scriptSelect").value;
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const statusMessage = document.getElementById("statusMessage");

    if (!script || !startDate || !endDate) {
        statusMessage.textContent = "⚠️ Please fill in all fields.";
        return;
    }

    // Show "Running..." message
    statusMessage.textContent = "🔄 Running script... Please wait.";

    // Send the form data to the backend
    fetch("https://intercom-llm-buddy.onrender.com/run-script/", {
        method: "POST",
        mode: "cors",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            script_name: script,
            start_date: startDate,
            end_date: endDate
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.drive_url) {
            statusMessage.innerHTML = `✅ Script finished! <a href="${data.drive_url}" target="_blank">View file in Google Drive</a>`;
        } else {
            statusMessage.textContent = `✅ ${data.output}`;
        }
    })
    .catch(error => {
        console.error("API call failed:", error);
        statusMessage.textContent = `❌ Error: ${error.message}`;
    });
}

// Attach submit handler to form
document.getElementById("scriptForm").addEventListener("submit", submitSelection);
