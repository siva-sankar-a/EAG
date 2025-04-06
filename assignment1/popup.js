document.addEventListener('DOMContentLoaded', function() {
  const startButton = document.getElementById('startButton');
  const nextButton = document.getElementById('nextButton');
  const prevButton = document.getElementById('prevButton');
  const statusDiv = document.getElementById('status');
  const transcriptionDiv = document.getElementById('transcription');
  let isListening = false;

  // Check if we can access the current tab
  async function getCurrentTab() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0];
  }

  // Function to check if we can inject the content script
  async function ensureContentScriptInjected() {
    try {
      const tab = await getCurrentTab();
      
      // Try to send a test message
      const response = await chrome.tabs.sendMessage(tab.id, { action: "ping" }).catch(() => false);
      
      if (!response) {
        // If the content script isn't loaded, inject it
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js']
        });
        
        // Wait a bit for the script to initialize
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      return true;
    } catch (error) {
      statusDiv.textContent = "Error: Cannot access this page. Try a different page.";
      return false;
    }
  }

  async function initializeNavigation() {
    const tab = await getCurrentTab();
    
    if (!tab.url.startsWith('http')) {
      statusDiv.textContent = "Error: This extension only works on web pages.";
      return false;
    }

    // Ensure content script is loaded before proceeding
    const isReady = await ensureContentScriptInjected();
    return isReady;
  }

  // Initialize when popup opens
  initializeNavigation();

  startButton.addEventListener('click', async function() {
    const tab = await getCurrentTab();
    
    if (!tab.url.startsWith('http')) {
      statusDiv.textContent = "Error: This extension only works on web pages.";
      return;
    }

    if (!isListening) {
      // Ensure content script is loaded before proceeding
      const isReady = await ensureContentScriptInjected();
      if (!isReady) return;

      try {
        await chrome.tabs.sendMessage(tab.id, {action: "startListening"});
        startButton.textContent = "Stop Voice Recognition";
        statusDiv.textContent = "Listening...";
        statusDiv.classList.add('listening');
        isListening = true;
      } catch (error) {
        statusDiv.textContent = "Error: Could not start voice recognition.";
        console.error(error);
      }
    } else {
      try {
        await chrome.tabs.sendMessage(tab.id, {action: "stopListening"});
        startButton.textContent = "Start Voice Recognition";
        statusDiv.textContent = "Click the button to start";
        statusDiv.classList.remove('listening');
        isListening = false;
        transcriptionDiv.textContent = '';
      } catch (error) {
        statusDiv.textContent = "Error: Could not stop voice recognition.";
        console.error(error);
      }
    }
  });

  nextButton.addEventListener('click', async function() {
    const tab = await getCurrentTab();
    try {
      await chrome.tabs.sendMessage(tab.id, {action: "nextInput"});
    } catch (error) {
      statusDiv.textContent = "Error: Could not navigate to next input.";
      console.error(error);
    }
  });

  prevButton.addEventListener('click', async function() {
    const tab = await getCurrentTab();
    try {
      await chrome.tabs.sendMessage(tab.id, {action: "previousInput"});
    } catch (error) {
      statusDiv.textContent = "Error: Could not navigate to previous input.";
      console.error(error);
    }
  });

  // Listen for status updates from content script
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "status") {
      if (message.text.startsWith('Heard: ')) {
        // Update transcription for interim results
        transcriptionDiv.textContent = message.text.substring(7);
        transcriptionDiv.className = 'interim';
      } else {
        statusDiv.textContent = message.text;
        if (message.text === 'Listening...') {
          transcriptionDiv.textContent = '';
          transcriptionDiv.className = '';
        }
      }
    }
  });
}); 