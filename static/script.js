// Function to handle form submission
function submitSelection(event) {
    event.preventDefault(); // Prevent form reload

    const script = document.getElementById("scriptSelect").value;
    let startDate = document.getElementById("startDate").value; // raw value from datetime-local
    let endDate = document.getElementById("endDate").value;   // raw value from datetime-local
    const storageMode = document.getElementById("storageMode").value;
    const statusMessage = document.getElementById("statusMessage");
    const fileLinks = document.getElementById("fileLinks");

    if (!script || !startDate || !endDate) {
        if (statusMessage) statusMessage.textContent = "⚠️ Please fill in all fields.";
        return;
    }

    // Show "Running..." message
    if (statusMessage) statusMessage.textContent = "🔄 Running script... Please wait.";
    if (fileLinks) fileLinks.innerHTML = ""; // Clear previous file links

    // Convert "YYYY-MM-DDTHH:MM" from datetime-local to "YYYY-MM-DD HH:MM" for the backend
    if (startDate && startDate.includes('T')) {
        startDate = startDate.replace('T', ' ');
    }
    if (endDate && endDate.includes('T')) {
        endDate = endDate.replace('T', ' ');
    }

    // Send the form data to the backend
    fetch("/run-script/", {
        method: "POST",
        mode: "cors",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            script_name: script,
            start_date: startDate,
            end_date: endDate,
            upload_to_gdrive: storageMode === "gdrive"
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === "success" || data.status === "no_data") {
            statusMessage.textContent = `✅ ${data.output || data.message || 'Request processed.'}`;
            
            let linksHtml = "";
            // Display file links based on storage mode and structure
            if (data.storage_mode === "gdrive" && data.gdrive_urls && data.gdrive_urls.length > 0) {
                linksHtml += '<h4>Google Drive Links:</h4>';
                data.gdrive_urls.forEach(url => {
                    const fileName = url.substring(url.lastIndexOf('/') + 1); 
                    linksHtml += `<a href="${url}" target="_blank" class="file-link">📁 ${fileName || url}</a>`;
                });
            } else if (data.storage_mode === "local" && data.local_files && data.local_files.length > 0) {
                linksHtml += "<h4>Generated Files (Local):</h4>";
                data.local_files.forEach(file => {
                    const fileName = file.split('/').pop().split('\\').pop();
                    linksHtml += `<div class="file-link">📁 ${fileName}</div>`;
                });
            } else if (data.file) { // Fallback for single 'file' property if present
                 linksHtml += `<h4>File:</h4><a href="${data.file}" target="_blank" class="file-link">📁 View File</a>`;
            }
            fileLinks.innerHTML = linksHtml;

        } else {
            if (statusMessage) statusMessage.textContent = `❌ ${data.error || data.output || "An error occurred"}`;
        }
    })
    .catch(error => {
        console.error("API call failed for scriptForm:", error);
        if (statusMessage) statusMessage.textContent = `❌ Error: ${error.message}`;
    });
}

// Attach submit handler to form
const scriptForm = document.getElementById("scriptForm");
if (scriptForm) {
    scriptForm.addEventListener("submit", submitSelection);
}

// --- NEW LOGIC FOR LLM5 COMPREHENSIVE ANALYSIS FORM ---
document.addEventListener('DOMContentLoaded', async () => {
    const llm5Form = document.getElementById('llm5Form');
    if (!llm5Form) return; 

    const targetTeamSelect = document.getElementById('targetTeamLlm5');
    const statusMessageLlm5Div = document.getElementById('statusMessageLlm5');
    const fileLinksLlm5Div = document.getElementById('fileLinksLlm5');
    const loaderLlm5Div = document.getElementById('loaderLlm5');
    const progressContainerLlm5 = document.getElementById('progressContainerLlm5');
    const progressBarLlm5 = document.getElementById('progressBarLlm5');
    const progressTallyLlm5 = document.getElementById('progressTallyLlm5');
    let wittyMessageIntervalId = null;
    let simulatedProgressIntervalId = null; // For progress simulation

    // ADD THIS BLOCK FOR DEBUGGING
    console.log("DOMContentLoaded: Checking for progress elements:");
    console.log("progressContainerLlm5:", progressContainerLlm5);
    console.log("progressBarLlm5:", progressBarLlm5);
    console.log("progressTallyLlm5:", progressTallyLlm5);
    // END DEBUGGING BLOCK

    // --- Dynamically populate Target Team dropdown ---
    if (targetTeamSelect) {
        try {
            console.log("Fetching teams for dropdown...");
            const response = await fetch("/api/teams"); // Use your actual API base URL
            if (!response.ok) {
                throw new Error(`Failed to fetch teams: ${response.status} ${response.statusText}`);
            }
            const teamsMap = await response.json(); // Expects { "Team Name A": "id1", "Team Name B": "id2" }
            console.log("Teams fetched:", teamsMap);

            // Clear existing options except for "All Teams"
            while (targetTeamSelect.options.length > 1) {
                targetTeamSelect.remove(1);
            }
            
            // Add fetched teams
            for (const teamName in teamsMap) {
                if (Object.prototype.hasOwnProperty.call(teamsMap, teamName)) {
                    const option = document.createElement('option');
                    option.value = teamName; // Value sent to backend is the Team Name
                    option.textContent = teamName;
                    targetTeamSelect.appendChild(option);
                }
            }
            // Re-add Unclassified if it's not in the fetched list and you want it
            // Or rely on LLM5.py's Unclassified handling
            const unclassifiedOption = document.createElement('option');
            unclassifiedOption.value = "Unclassified";
            unclassifiedOption.textContent = "Unclassified";
            targetTeamSelect.appendChild(unclassifiedOption);

            console.log("Team dropdown populated.");

        } catch (error) {
            console.error("Error populating team dropdown:", error);
            if (statusMessageLlm5Div) { // Use the LLM5 status message div for this error too
                statusMessageLlm5Div.textContent = `⚠️ Error loading team list: ${error.message}. Dropdown may be incomplete.`;
                statusMessageLlm5Div.className = 'error'; // Use error styling
            }
            // Fallback: ensure some basic options exist if API call fails, to prevent empty select
            // This might be redundant if HTML already has them, but good for robustness
            if (targetTeamSelect.options.length <= 1) { // If only "All Teams" or empty
                const fallbackTeams = ["MetaMask TS", "Card", "Portfolio", "Solana", "MetaMask UST", "MetaMask HD General", "Unclassified"];
                fallbackTeams.forEach(name => {
                    const option = document.createElement('option');
                    option.value = name;
                    option.textContent = name;
                    targetTeamSelect.appendChild(option);
                });
                console.warn("Populated team dropdown with fallback static list due to API error.");
            }
        }
    }
    // --- End of dynamic dropdown population ---

    const wittyMessages = [
        "Connecting to Intercom's data matrix...",
        "Analyzing conversation streams...",
        "Summoning insights from the digital ether...",
        "Filtering for actionable intelligence...",
        "Compiling comprehensive team reports...",
        "Cross-referencing user sentiment...",
        "Polishing data diamonds...",
        "Preparing GDrive warp sequence...",
        "Assembling AI sub-routines...",
        "Reticulating splines...",
        "Calibrating flux capacitors...",
        "Querying the oracle...",
        "Engaging heuristic algorithms...",
        "Finalizing enlightenment packet..."
    ];

    function showWittyMessage() {
        if (statusMessageLlm5Div) {
            const randomIndex = Math.floor(Math.random() * wittyMessages.length);
            statusMessageLlm5Div.textContent = wittyMessages[randomIndex];
            statusMessageLlm5Div.className = 'status-running'; // Add class for specific styling
        }
    }

    llm5Form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if(loaderLlm5Div) loaderLlm5Div.style.display = 'block';
        if(progressContainerLlm5) progressContainerLlm5.style.display = 'block';
        if(progressBarLlm5) {
            progressBarLlm5.style.width = '0%';
            progressBarLlm5.textContent = '0%';
        }
        if(progressTallyLlm5) progressTallyLlm5.textContent = 'Initializing...';
        if(fileLinksLlm5Div) fileLinksLlm5Div.innerHTML = ''; // Clear previous links
        if(statusMessageLlm5Div) statusMessageLlm5Div.textContent = ''; // Clear previous status

        showWittyMessage(); 
        if (wittyMessageIntervalId) clearInterval(wittyMessageIntervalId);
        wittyMessageIntervalId = setInterval(showWittyMessage, 2500);

        const selectedTimeframe = document.getElementById('timeframeLlm5').value;
        const storageMode = document.getElementById('storageModeLlm5').value;
        const targetTeam = document.getElementById('targetTeamLlm5').value;
        const targetProductArea = document.getElementById('targetProductAreaLlm5').value;

        if (!selectedTimeframe) {
            if (wittyMessageIntervalId) clearInterval(wittyMessageIntervalId);
            if(statusMessageLlm5Div) {
                statusMessageLlm5Div.textContent = '❌ Please select a timeframe.';
                statusMessageLlm5Div.className = 'error';
            }
            if(loaderLlm5Div) loaderLlm5Div.style.display = 'none';
            if(progressContainerLlm5) progressContainerLlm5.style.display = 'none';
            return;
        }
        
        const requestData = {
            script_name: "LLM5.py",
            timeframe_preset: selectedTimeframe, 
            upload_to_gdrive: storageMode === 'gdrive',
            target_team: targetTeam,
            target_product_area: targetProductArea
        };

        let currentSimulatedProgress = 0;
        const maxSimulatedProgress = 95; 
        const progressIncrement = 5;

        if(progressBarLlm5) {
             progressBarLlm5.style.width = currentSimulatedProgress + '%'; 
             progressBarLlm5.textContent = currentSimulatedProgress + '%';
        }
        if(progressTallyLlm5) progressTallyLlm5.textContent = 'Fetching conversations...';

        if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId);
        simulatedProgressIntervalId = setInterval(() => {
            if (currentSimulatedProgress < maxSimulatedProgress) {
                currentSimulatedProgress += progressIncrement;
                if (currentSimulatedProgress > maxSimulatedProgress) currentSimulatedProgress = maxSimulatedProgress;

                if(progressBarLlm5) {
                    progressBarLlm5.style.width = currentSimulatedProgress + '%';
                    progressBarLlm5.textContent = currentSimulatedProgress + '%';
                }
                if(progressTallyLlm5) {
                    let tallyMsg = 'Working...';
                    if (currentSimulatedProgress < 20) tallyMsg = 'Fetching conversations...';
                    else if (currentSimulatedProgress < 50) tallyMsg = 'Analyzing data & identifying insights...';
                    else if (currentSimulatedProgress < 80) tallyMsg = 'Generating reports and files...';
                    else tallyMsg = 'Finalizing and preparing results...';
                    progressTallyLlm5.textContent = tallyMsg;
                }
            } else {
                if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId);
            }
        }, 1000); // Faster simulation interval

        try {
            const response = await fetch("/run-script/", {
                method: 'POST',
                mode: "cors",
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData),
            });

            if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId); // Stop simulation once response starts processing

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: 'Failed to parse error response from server.' }));
                throw new Error(`Server error ${response.status}: ${errorData.error || response.statusText}`);
            }

            const result = await response.json();

            if (statusMessageLlm5Div) {
                if (result.status === 'success') {
                    statusMessageLlm5Div.textContent = '✅ Report complete! Files are available below.';
                    statusMessageLlm5Div.className = 'success';
                } else if (result.status === 'no_data') {
                    statusMessageLlm5Div.textContent = `✅ ${result.message || 'Completed. No data found for the criteria.'}`;
                    statusMessageLlm5Div.className = 'no_data';
                } else if (result.message || result.output) { // Other successful type messages from backend
                    statusMessageLlm5Div.textContent = `✅ ${result.output || result.message}`;
                    statusMessageLlm5Div.className = 'success';
                } else { // Fallback for unhandled success cases
                    statusMessageLlm5Div.textContent = '✅ Request processed successfully.';
                    statusMessageLlm5Div.className = 'success';
                }
            }
                
            if (result.status === 'success' || result.status === 'no_data') {
                if(progressBarLlm5) {
                    progressBarLlm5.style.width = '100%';
                    progressBarLlm5.textContent = '100%';
                }
                if(progressTallyLlm5 && result.processed_counts) {
                    const counts = result.processed_counts;
                    let tallyMsg = `Completed. Fetched: ${counts.total_conversations_fetched === undefined ? 'N/A' : counts.total_conversations_fetched}. `;
                    const teamEoSCount = counts.team_eos_reports_generated || 0;
                    const targetedComboFiles = counts.targeted_team_product_area_files || 0;
                    const teamSpecificAreaFiles = counts.team_specific_product_area_files || 0;
                    const globalAreaFiles = counts.global_product_area_files || 0;
                    const overallEoS = counts.overall_eos_report_generated || 0;
                    
                    let fileDetails = [];
                    if (teamEoSCount > 0) fileDetails.push(`Team EoS: ${teamEoSCount}`);
                    if (targetedComboFiles > 0) fileDetails.push(`Targeted Sets: ${targetedComboFiles}`);
                    if (teamSpecificAreaFiles > 0) fileDetails.push(`Team Area Sets: ${teamSpecificAreaFiles}`);
                    if (globalAreaFiles > 0) fileDetails.push(`Global Area Sets: ${globalAreaFiles}`);
                    if (overallEoS > 0) fileDetails.push(`Overall EoS: ${overallEoS}`);

                    if (fileDetails.length > 0) {
                        tallyMsg += `Generated: ${fileDetails.join(', ')}.`;
                    } else if (result.status !== 'no_data'){
                        tallyMsg += "No specific files generated based on returned counts.";
                    }
                     if (result.status === 'no_data') tallyMsg = "Completed. No data found for the criteria.";

                    progressTallyLlm5.textContent = tallyMsg;
                } else if (progressTallyLlm5) {
                    progressTallyLlm5.textContent = "Processing complete. Detailed counts unavailable.";
                }
            } else { // Backend reported an issue not covered by success/no_data (e.g., 'failed' status)
                if(statusMessageLlm5Div && result.message) { // Display backend's specific error message
                     statusMessageLlm5Div.textContent = `❌ ${result.message}`;
                     statusMessageLlm5Div.className = 'error';
                }
                if(progressContainerLlm5) progressContainerLlm5.style.display = 'none';
            }

            let linksHtml = '';
            if (result.gdrive_urls && result.gdrive_urls.length > 0) {
                linksHtml += '<h4>Google Drive Links:</h4>';
                result.gdrive_urls.forEach(url => {
                    const fileName = url.substring(url.lastIndexOf('/') + 1) || url;
                    linksHtml += `<a href="${url}" target="_blank" class="file-link" download="${fileName}">${fileName}</a>`;
                });
            }
            if (result.local_files && result.local_files.length > 0) { 
                linksHtml += "<h4>Generated Files (Local):</h4>";
                result.local_files.forEach(filePath => {
                    const fileName = filePath.split('/').pop().split('\\').pop(); 
                    // Assuming files are served from a /download/ endpoint
                    linksHtml += `<a href="/download/${encodeURIComponent(fileName)}" class="file-link" download="${fileName}">${fileName}</a>`;
                });
            }
            if(fileLinksLlm5Div) fileLinksLlm5Div.innerHTML = linksHtml;

        } catch (error) {
            if(statusMessageLlm5Div) {
                statusMessageLlm5Div.textContent = `❌ Client-side Error: ${error.message}`;
                statusMessageLlm5Div.className = 'error';
            }
            if(progressContainerLlm5) progressContainerLlm5.style.display = 'none'; // Hide progress on client error
            console.error('API Call Error for LLM5Form:', error);
        } finally {
            if (wittyMessageIntervalId) clearInterval(wittyMessageIntervalId);
            if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId); // Ensure simulation stops
            if(loaderLlm5Div) loaderLlm5Div.style.display = 'none';
        }
    });
});
