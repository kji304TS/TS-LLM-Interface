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
    const targetProductAreaSelect = document.getElementById('targetProductAreaLlm5');
    const productAreaLabel = document.querySelector("label[for='targetProductAreaLlm5']"); // Get the label
    const statusMessageLlm5Div = document.getElementById('statusMessageLlm5');
    const fileLinksLlm5Div = document.getElementById('fileLinksLlm5');
    const loaderLlm5Div = document.getElementById('loaderLlm5');
    const progressContainerLlm5 = document.getElementById('progressContainerLlm5');
    const progressBarLlm5 = document.getElementById('progressBarLlm5');
    const progressTallyLlm5 = document.getElementById('progressTallyLlm5');
    let wittyMessageIntervalId = null;
    let simulatedProgressIntervalId = null; // For progress simulation
    let currentLocalFiles = []; // Store the list of local files from the last run

    // ADD THIS BLOCK FOR DEBUGGING
    console.log("DOMContentLoaded: Checking for progress elements:");
    console.log("progressContainerLlm5:", progressContainerLlm5);
    console.log("progressBarLlm5:", progressBarLlm5);
    console.log("progressTallyLlm5:", progressTallyLlm5);
    // END DEBUGGING BLOCK

    // --- NEW: Store original product area options ---
    let originalProductAreaOptions = [];
    if (targetProductAreaSelect) {
        originalProductAreaOptions = Array.from(targetProductAreaSelect.options).map(opt => ({
            value: opt.value,
            text: opt.textContent,
            selected: opt.selected, // Preserve original selection state if needed for "All Areas"
            disabled: opt.disabled
        }));
    }
    // --- END NEW ---

    // Renamed and expanded function
    function updateConditionalFieldsVisibility() {
        if (!targetTeamSelect || !targetProductAreaSelect || !productAreaLabel) {
            console.warn("Core select elements for conditional visibility not found.");
            return;
        }
        const selectedTeam = targetTeamSelect.value;

        let showProductAreaDropdown = true; // Default to showing, specific cases will hide it
        let productAreaOptionsToDisplay = [];
        let defaultProductAreaValue = ""; 

        // Determine visibility and options for Target Product Area
        if (["MetaMask HD General", "MetaMask HD Solana", "MetaMask HD Portfolio"].includes(selectedTeam)) {
            showProductAreaDropdown = true;
            // Filter out "Security" for these specific teams
            productAreaOptionsToDisplay = originalProductAreaOptions.filter(opt => opt.value !== "Security");
            const allAreasOption = productAreaOptionsToDisplay.find(opt => opt.value === "ALL_AREAS");
            defaultProductAreaValue = allAreasOption ? allAreasOption.value : (productAreaOptionsToDisplay.length > 0 ? productAreaOptionsToDisplay[0].value : "");
        } else if (["ALL_TEAMS", "Unclassified"].includes(selectedTeam)) { // These show all options, including Security
            showProductAreaDropdown = true;
            productAreaOptionsToDisplay = originalProductAreaOptions; 
            const allAreasOption = originalProductAreaOptions.find(opt => opt.value === "ALL_AREAS");
            defaultProductAreaValue = allAreasOption ? allAreasOption.value : (originalProductAreaOptions.length > 0 ? originalProductAreaOptions[0].value : "");
        } else if (selectedTeam === "MetaMask HD Card") {
            showProductAreaDropdown = true;
            const cardOption = originalProductAreaOptions.find(opt => opt.value === "Card");
            if (cardOption) productAreaOptionsToDisplay.push(cardOption);
            else console.warn("'Card' option not found in originalProductAreaOptions for MetaMask HD Card team.");
            defaultProductAreaValue = "Card";
        } else if (["MetaMask HD UST", "MetaMask TS UST"].includes(selectedTeam)) {
            showProductAreaDropdown = true;
            const securityOption = originalProductAreaOptions.find(opt => opt.value === "Security");
            if (securityOption) productAreaOptionsToDisplay.push(securityOption);
            else console.warn("'Security' option not found in originalProductAreaOptions for UST teams.");
            defaultProductAreaValue = "Security";
        } else if (selectedTeam === "Phosphor TS") { 
            showProductAreaDropdown = false;
        } else { 
            // For any other teams not explicitly handled (e.g. "MetaMask TS" if it were standalone), hide by default
            showProductAreaDropdown = false;
        }

        // Apply visibility and populate options for Target Product Area
        if (showProductAreaDropdown) {
            targetProductAreaSelect.style.display = '';
            productAreaLabel.style.display = '';
            targetProductAreaSelect.disabled = false;

            targetProductAreaSelect.innerHTML = ''; // Clear current options
            if (productAreaOptionsToDisplay.length > 0) {
                productAreaOptionsToDisplay.forEach(optData => {
                    const option = document.createElement('option');
                    option.value = optData.value;
                    option.textContent = optData.text;
                    option.disabled = optData.disabled;
                    targetProductAreaSelect.appendChild(option);
                });
                targetProductAreaSelect.value = defaultProductAreaValue;
                 // Fallback if defaultProductAreaValue is not among the optionsToShow (e.g. "Card" option was missing from original)
                if (!targetProductAreaSelect.value && targetProductAreaSelect.options.length > 0) {
                    targetProductAreaSelect.value = targetProductAreaSelect.options[0].value;
                }
            } else {
                // No options to display, maybe add a "N/A" or leave empty
                const noOption = document.createElement('option');
                noOption.value = "";
                noOption.textContent = "N/A for this team";
                noOption.disabled = true;
                targetProductAreaSelect.appendChild(noOption);
                targetProductAreaSelect.value = "";
            }
        } else {
            targetProductAreaSelect.style.display = 'none';
            productAreaLabel.style.display = 'none';
            targetProductAreaSelect.disabled = true;
            targetProductAreaSelect.innerHTML = ''; // Clear options
            targetProductAreaSelect.value = ""; 
        }
    }

    if (targetTeamSelect) {
        targetTeamSelect.addEventListener('change', updateConditionalFieldsVisibility); // Use renamed function
    }
    // --- End Conditional Product Area Logic ---

    // --- Statically populate Target Team dropdown ---
    if (targetTeamSelect) {
        try {
            console.log("Statically populating teams for dropdown...");

            // Clear existing options except for a potential "All Teams" if it's the first one.
            // Assuming "All Teams" is the first option and should be preserved.
            // If "All Teams" is not the first or should be re-added, adjust accordingly.
            while (targetTeamSelect.options.length > 1) { // Keep the first option (e.g., "All Teams")
                targetTeamSelect.remove(1);
            }

            const primaryTeams = [
                "MetaMask HD General",
                "MetaMask HD Solana",
                "MetaMask HD Card",
                "MetaMask HD Portfolio",
                "MetaMask HD UST",
                "MetaMask TS UST",
                "Phosphor TS"
            ];

            primaryTeams.forEach(teamName => {
                const option = document.createElement('option');
                option.value = teamName;
                option.textContent = teamName;
                targetTeamSelect.appendChild(option);
            });

            // Add Unclassified
            const unclassifiedOption = document.createElement('option');
            unclassifiedOption.value = "Unclassified";
            unclassifiedOption.textContent = "Unclassified";
            targetTeamSelect.appendChild(unclassifiedOption);

            // Add commented-out options for other teams
            const commentedOutHtml = `
                <!--
                <option value="Another Team 1">Another Team 1</option>
                <option value="Another Team 2">Another Team 2</option>
                <option value="Card">Card</option>
                <option value="Portfolio">Portfolio</option>
                <option value="Solana">Solana</option>
                <option value="MetaMask UST">MetaMask UST</option>
                <option value="MetaMask TS">MetaMask TS</option> 
                -->
            `;
            // This is a bit tricky with direct DOM manipulation for comments.
            // A common approach is to have them in the HTML, or log them if needed for devs.
            // For this exercise, I'll log it and ensure the select HTML can be manually updated.
            console.log("To add more teams, uncomment or add options in the HTML or edit script.js. Example structure for HTML:", commentedOutHtml);


            console.log("Team dropdown populated statically.");

            // Initial call to set product area state after teams are populated and default team is set
            updateConditionalFieldsVisibility(); // Use renamed function

        } catch (error) {
            console.error("Error populating team dropdown statically:", error);
            if (statusMessageLlm5Div) {
                statusMessageLlm5Div.textContent = `⚠️ Error initializing team list: ${error.message}. Dropdown may be incomplete.`;
                statusMessageLlm5Div.className = 'error';
            }
            // Minimal fallback if even static population fails (should be rare)
            if (targetTeamSelect.options.length <= 1) {
                const basicFallback = ["Unclassified"];
                basicFallback.forEach(name => {
                    const option = document.createElement('option');
                    option.value = name;
                    option.textContent = name;
                    targetTeamSelect.appendChild(option);
                });
                console.warn("Populated team dropdown with minimal fallback due to an unexpected error during static population.");
            }
        }
    }
    // --- End of static dropdown population ---

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
            target_team: targetTeam === "ALL_TEAMS" ? null : targetTeam, // Send null if ALL_TEAMS
            target_product_area: targetProductArea === "ALL_AREAS" ? null : targetProductArea // Send null if ALL_AREAS
        };

        let currentSimulatedProgress = 0;
        const maxSimulatedProgress = 95; 
        // --- NEW: More granular progress stages ---
        const progressStages = [
            { percent: 0, message: `Running for: ${selectedTimeframe}, Team: ${targetTeam}, Area: ${targetProductArea}` },
            { percent: 5, message: "Initializing analysis..." },
            { percent: 15, message: "Fetching Intercom team data..." },
            { percent: 25, message: "Searching conversations (this may take a moment)..." },
            { percent: 50, message: "Processing fetched conversations..." },
            { percent: 70, message: "Analyzing data and generating insights..." },
            { percent: 85, message: "Creating report files..." },
            { percent: 90, message: storageMode === 'gdrive' ? "Preparing GDrive upload..." : "Finalizing local files..." },
            { percent: maxSimulatedProgress, message: "Finalizing..." }
        ];
        let currentStageIndex = 0;
        // --- END NEW ---

        if(progressBarLlm5) {
             progressBarLlm5.style.width = currentSimulatedProgress + '%'; 
             progressBarLlm5.textContent = currentSimulatedProgress + '%';
        }
        // Display initial user selections
        if(progressTallyLlm5) progressTallyLlm5.textContent = `Targeting: ${selectedTimeframe} | Team: ${targetTeam} | Product Area: ${targetProductArea}`;

        if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId);
        simulatedProgressIntervalId = setInterval(() => {
            if (currentStageIndex < progressStages.length -1) { // Stop before the absolute final simulated stage
                currentStageIndex++;
                currentSimulatedProgress = progressStages[currentStageIndex].percent;
                if(progressBarLlm5) {
                    progressBarLlm5.style.width = currentSimulatedProgress + '%';
                    progressBarLlm5.textContent = currentSimulatedProgress + '%';
                }
                if(progressTallyLlm5) {
                    progressTallyLlm5.textContent = progressStages[currentStageIndex].message;
                }
            } else {
                if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId); 
            }
        // }, 1000); // Faster simulation interval - Adjusted to be slightly longer for more distinct messages
        }, 1800); // Interval for simulated progress messages

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
                    statusMessageLlm5Div.textContent = '✅ Report generation complete! See details and file links below.';
                    statusMessageLlm5Div.className = 'success';
                } else if (result.status === 'no_data') {
                    statusMessageLlm5Div.textContent = `ℹ️ ${result.message || 'Completed. No data found for the specified criteria.'}`;
                    statusMessageLlm5Div.className = 'no_data'; // Use a specific class for no_data if styled differently
                } else if (result.status === 'no_files_for_target'){
                    statusMessageLlm5Div.textContent = `ℹ️ ${result.message || 'Completed. No files were generated for the specific targets.'}`;
                    statusMessageLlm5Div.className = 'no_data'; 
                } else if (result.message || result.output) { // Other successful type messages from backend
                    statusMessageLlm5Div.textContent = `✅ ${result.output || result.message}`;
                    statusMessageLlm5Div.className = 'success';
                } else { // Fallback for unhandled success cases
                    statusMessageLlm5Div.textContent = '✅ Request processed successfully.';
                    statusMessageLlm5Div.className = 'success';
                }
            }
                
            if (result.status === 'success' || result.status === 'no_data' || result.status === 'no_files_for_target') {
                if(progressBarLlm5) {
                    progressBarLlm5.style.width = '100%';
                    progressBarLlm5.textContent = '100%';
                }
                if(progressTallyLlm5 && result.processed_counts) {
                    const counts = result.processed_counts;
                    let tallyHtml = "<strong>Processing Summary:</strong><br>";
                    const countLabels = {
                        total_conversations_fetched: "Total Conversations Fetched",
                        targeted_team_product_area_files: "Targeted Team & Area File Sets",
                        team_eos_reports_generated: "Team End-of-Shift Reports",
                        team_specific_product_area_files: "Team-Specific Product Area File Sets",
                        global_product_area_files: "Global Product Area File Sets",
                        overall_eos_report_generated: "Overall End-of-Shift Reports",
                        unclassified_team_skipped: "Unclassified Team Skipped (No Data)"
                    };

                    for (const key in counts) {
                        if (Object.hasOwnProperty.call(counts, key)) {
                            const label = countLabels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                            const value = counts[key];
                            if (value !== undefined && value !== null && (typeof value !== 'boolean' || value === true)) { // Display numbers and true booleans
                                tallyHtml += `${label}: ${value}<br>`;
                            }
                        }
                    }
                    if (tallyHtml === "<strong>Processing Summary:</strong><br>") { // No counts were added
                        tallyHtml += (result.status === 'no_data' || result.status === 'no_files_for_target') ? (result.message || "No data processed.") : "No specific counts available.";
                    }
                    progressTallyLlm5.innerHTML = tallyHtml;
                } else if (progressTallyLlm5) {
                    progressTallyLlm5.textContent = result.message || "Processing complete. Detailed counts unavailable.";
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
                currentLocalFiles = result.local_files; // Store for zipping
                linksHtml += "<h4>Generated Files (Local):</h4>";
                result.local_files.forEach(filePath => {
                    const fileName = filePath.split('/').pop().split('\\').pop(); 
                    // Assuming files are served from a /download/ endpoint
                    linksHtml += `<a href="/download/${encodeURIComponent(fileName)}" class="file-link" download="${fileName}">${fileName}</a>`;
                });
                if (fileLinksLlm5Div) fileLinksLlm5Div.innerHTML = linksHtml;
                if (downloadZipButton && currentLocalFiles.length > 0) {
                    downloadZipButton.style.display = "block"; // Show zip button
                }
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

    // Event listener for the zip button
    const downloadZipButton = document.getElementById('downloadZipButton');
    if (downloadZipButton) {
        downloadZipButton.addEventListener('click', async () => {
            if (currentLocalFiles.length === 0) {
                alert("No files to zip.");
                return;
            }
            console.log("Zipping files:", currentLocalFiles);
            try {
                const response = await fetch("/download-zip/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ filenames: currentLocalFiles }),
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: "Unknown error during zipping" }));
                    throw new Error(`Failed to download zip: ${response.status} ${response.statusText}. ${errorData.detail}`);
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.style.display = "none";
                a.href = url;
                // Extract filename from Content-Disposition header if possible
                const disposition = response.headers.get('Content-Disposition');
                let filename = "ibuddy_reports.zip"; // Default
                if (disposition && disposition.indexOf('attachment') !== -1) {
                    const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                    const matches = filenameRegex.exec(disposition);
                    if (matches != null && matches[1]) {
                        filename = matches[1].replace(/['"]/g, '');
                    }
                }
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                a.remove();
            } catch (error) {
                console.error("Error downloading zip:", error);
                const statusMessage = document.getElementById("statusMessage");
                if (statusMessage) statusMessage.textContent = `❌ Error downloading zip: ${error.message}`;
            }
        });
    }
});
