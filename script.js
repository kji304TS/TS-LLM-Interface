const statusMessageLlm5Div = document.getElementById('statusMessageLlm5');
const fileLinksLlm5Div = document.getElementById('fileLinksLlm5');
const loaderLlm5Div = document.getElementById('loaderLlm5');
const progressContainerLlm5 = document.getElementById('progressContainerLlm5');
const progressBarLlm5 = document.getElementById('progressBarLlm5');
const progressTallyLlm5 = document.getElementById('progressTallyLlm5');
let wittyMessageIntervalId = null;
let simulatedProgressIntervalId = null; // For progress simulation

const wittyMessages = [
    "Connecting to Intercom's data matrix...", "Analyzing conversation streams...",
    "Summoning insights from the digital ether...", "Filtering for actionable intelligence...",
    "Compiling comprehensive team reports...", "Cross-referencing user sentiment...",
    "Polishing data diamonds...", "Preparing GDrive warp sequence...",
    "Assembling AI sub-routines...", "Reticulating splines...",
    "Calibrating flux capacitors...", "Querying the oracle...",
    "Engaging heuristic algorithms...", "Finalizing enlightenment packet..."
];

function showWittyMessage() {
    if (statusMessageLlm5Div) {
        const randomIndex = Math.floor(Math.random() * wittyMessages.length);
        statusMessageLlm5Div.textContent = wittyMessages[randomIndex];
        statusMessageLlm5Div.className = 'status-running'; 
    }
}

llm5Form.addEventListener('submit', async (event) => {
    event.preventDefault(); 

    if(loaderLlm5Div) loaderLlm5Div.style.display = 'block';
    if(progressContainerLlm5) progressContainerLlm5.style.display = 'block';
    let currentSimulatedProgress = 0;
    let simulatedProductAreas = 0;
    let simulatedTeamReports = 0;
    const estimatedTotalProductAreas = 12; // Based on CATEGORY_HEADERS
    const estimatedTotalTeamReports = 5;  // Based on your team setup
    const progressIncrement = 5; // How much to increment progress bar per step
    const maxSimulatedProgress = 90; // Don't let simulation exceed this before backend responds

    if(progressBarLlm5) {
        progressBarLlm5.style.width = '0%';
        progressBarLlm5.textContent = '0%';
    }
    if(progressTallyLlm5) progressTallyLlm5.textContent = 'Preparing to analyze...';
    if(statusMessageLlm5Div) statusMessageLlm5Div.textContent = ''; 
    if(fileLinksLlm5Div) fileLinksLlm5Div.innerHTML = '';
    
    if (wittyMessageIntervalId) clearInterval(wittyMessageIntervalId);
    if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId);
    
    showWittyMessage(); 
    wittyMessageIntervalId = setInterval(showWittyMessage, 2500); // Slightly longer interval for witty messages

    const selectedTimeframe = document.getElementById('timeframeLlm5').value;
    const storageMode = document.getElementById('storageModeLlm5').value;

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
        upload_to_gdrive: storageMode === 'gdrive'
    };

    currentSimulatedProgress = 5; // Initial small progress
    if(progressBarLlm5) {
         progressBarLlm5.style.width = currentSimulatedProgress + '%'; 
         progressBarLlm5.textContent = currentSimulatedProgress + '%';
    }
    if(progressTallyLlm5) progressTallyLlm5.textContent = 'Fetching conversations...';

    simulatedProgressIntervalId = setInterval(() => {
        if (currentSimulatedProgress < maxSimulatedProgress) {
            currentSimulatedProgress += progressIncrement;
            if (currentSimulatedProgress > maxSimulatedProgress) currentSimulatedProgress = maxSimulatedProgress;

            if(progressBarLlm5) {
                progressBarLlm5.style.width = currentSimulatedProgress + '%';
                progressBarLlm5.textContent = currentSimulatedProgress + '%';
            }

            // Simulate tally increments
            if (simulatedProductAreas < estimatedTotalProductAreas) simulatedProductAreas++;
            if (currentSimulatedProgress > 30 && simulatedTeamReports < estimatedTotalTeamReports) simulatedTeamReports++; // Start team reports a bit later
            
            if(progressTallyLlm5) {
                progressTallyLlm5.textContent = `Analyzing... Product Areas: ${simulatedProductAreas}/${estimatedTotalProductAreas}, Team Reports: ${simulatedTeamReports}/${estimatedTotalTeamReports}`;
            }
        } else {
            if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId); 
        }
    }, 1500); // Update simulation every 1.5 seconds

    try {
        const response = await fetch("http://192.168.0.27:8080/run-script/", {
            method: 'POST',
            mode: "cors",
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData),
        });

        if (wittyMessageIntervalId) clearInterval(wittyMessageIntervalId);
        if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId); // Clear simulation interval on response
        if(loaderLlm5Div) loaderLlm5Div.style.display = 'none'; 

        if (!response.ok) {
            if(progressContainerLlm5) progressContainerLlm5.style.display = 'none'; // Hide progress bar
            if(progressTallyLlm5) progressTallyLlm5.textContent = 'Processing failed.';
            const errorData = await response.json().catch(() => ({ error: 'Failed to parse error response.' }));
            if(statusMessageLlm5Div) {
                statusMessageLlm5Div.textContent = `❌ Error: HTTP ${response.status} - ${errorData.error || response.statusText}`;
                statusMessageLlm5Div.className = 'error';
            }
            throw new Error(`HTTP error ${response.status}: ${errorData.error || response.statusText}`);
        }

        const result = await response.json();

        // Finalize progress bar
        if(progressBarLlm5) {
            progressBarLlm5.style.width = '100%';
            progressBarLlm5.textContent = '100%';
        }

        if (statusMessageLlm5Div) {
            statusMessageLlm5Div.textContent = `✅ ${result.output || result.message || 'Request processed.'}`;
            if (result.status === 'success') statusMessageLlm5Div.className = 'success';
            else if (result.status === 'no_data') statusMessageLlm5Div.className = 'no_data';
            else statusMessageLlm5Div.className = 'success'; 
        }
        
        // Display processed counts from backend
        if (result.processed_counts && progressTallyLlm5) {
            const counts = result.processed_counts;
            progressTallyLlm5.textContent = `Processing Summary: Product Areas: ${counts.product_areas !== undefined ? counts.product_areas : 'N/A'}, Team Reports: ${counts.team_reports !== undefined ? counts.team_reports : 'N/A'}.`;
        } else if (progressTallyLlm5) {
            progressTallyLlm5.textContent = 'Processing summary not available.';
        }
            
        let linksHtml = '';
        if (result.gdrive_urls && result.gdrive_urls.length > 0) {
            linksHtml += '<h4>Google Drive Links:</h4>';
            result.gdrive_urls.forEach(url => {
                const fileName = url.substring(url.lastIndexOf('/') + 1); 
                linksHtml += `<a href="${url}" target="_blank" class="file-link">${fileName || url}</a>`;
            });
        }
        if (result.local_files && result.local_files.length > 0) { 
            linksHtml += "<h4>Generated Files (Local):</h4>";
            result.local_files.forEach(file => {
                const fileName = file.split('/').pop().split('\\\\').pop(); 
                linksHtml += `<div class="file-link">${fileName} (Check 'Outputs' or 'output_files')</div>`;
            });
        }
        if(fileLinksLlm5Div) fileLinksLlm5Div.innerHTML = linksHtml;

    } catch (error) { // Catch network errors or errors from !response.ok
        if (wittyMessageIntervalId) clearInterval(wittyMessageIntervalId);
        if (simulatedProgressIntervalId) clearInterval(simulatedProgressIntervalId); // Clear simulation interval on error
        if(loaderLlm5Div) loaderLlm5Div.style.display = 'none';
        if(progressContainerLlm5) progressContainerLlm5.style.display = 'none';
        if(progressBarLlm5) { 
             progressBarLlm5.style.width = '0%'; // Reset on error
             progressBarLlm5.textContent = 'Error';
        }
        if(progressTallyLlm5) progressTallyLlm5.textContent = 'An error occurred during processing.';

        if(statusMessageLlm5Div && !statusMessageLlm5Div.textContent.startsWith('❌ Error:')) { // Avoid overwriting specific HTTP error
            statusMessageLlm5Div.textContent = `❌ Network or Script Error: ${error.message}`;
            statusMessageLlm5Div.className = 'error';
        }
        console.error('API Call Error for LLM5Form:', error);
    }
}); 