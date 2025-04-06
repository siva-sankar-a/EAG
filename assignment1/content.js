class FormNavigator {
  constructor() {
    this.currentInputIndex = -1;
    this.formInputs = [];
    this.recognition = null;
    this.isListening = false;
  }

  initialize() {
    if (!('webkitSpeechRecognition' in window)) {
      this.sendStatus('Speech recognition is not supported in this browser.');
      return false;
    }

    this.recognition = new webkitSpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = 'en-US';

    this.setupRecognitionHandlers();
    this.collectFormInputs();
    return true;
  }

  setupRecognitionHandlers() {
    this.recognition.onresult = (event) => {
      const last = event.results.length - 1;
      const text = event.results[last][0].transcript.trim().toLowerCase();
      
      // Send interim results to popup
      if (event.results[last].isFinal) {
        if (text === 'next') {
          this.moveToNextInput();
        } else if (text === 'previous') {
          this.moveToPreviousInput();
        } else {
          this.fillCurrentInput(text);
        }
      } else {
        // Send interim results to popup
        this.sendStatus('Heard: ' + text);
      }
    };

    this.recognition.onerror = (event) => {
      this.sendStatus('Error: ' + event.error);
      if (event.error === 'not-allowed') {
        this.stopListening();
      }
    };

    this.recognition.onend = () => {
      if (this.isListening) {
        try {
          this.recognition.start();
        } catch (error) {
          this.sendStatus('Error restarting recognition: ' + error.message);
          this.stopListening();
        }
      }
    };
  }

  startListening() {
    if (!this.recognition && !this.initialize()) {
      return;
    }
    
    try {
      this.recognition.start();
      this.isListening = true;
      this.sendStatus('Listening...');
    } catch (error) {
      this.sendStatus('Error starting recognition: ' + error.message);
      this.isListening = false;
    }
  }

  stopListening() {
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (error) {
        console.error('Error stopping recognition:', error);
      }
      this.isListening = false;
      this.sendStatus('Stopped listening');
    }
  }

  collectFormInputs() {
    // Get all input elements that can be filled
    this.formInputs = Array.from(document.querySelectorAll(
      'input[type="text"], input[type="email"], input[type="tel"], input[type="number"], input[type="search"], textarea'
    ));

    if (this.formInputs.length === 0) {
      this.sendStatus('No form inputs found on this page.');
      return false;
    }

    this.currentInputIndex = 0;
    this.highlightCurrentInput();
    return true;
  }

  moveToNextInput() {
    this.removeHighlight();
    this.currentInputIndex = (this.currentInputIndex + 1) % this.formInputs.length;
    this.highlightCurrentInput();
    this.sendStatus('Moved to next input');
  }

  moveToPreviousInput() {
    this.removeHighlight();
    this.currentInputIndex = (this.currentInputIndex - 1 + this.formInputs.length) % this.formInputs.length;
    this.highlightCurrentInput();
    this.sendStatus('Moved to previous input');
  }

  highlightCurrentInput() {
    if (this.currentInputIndex >= 0 && this.currentInputIndex < this.formInputs.length) {
      const currentInput = this.formInputs[this.currentInputIndex];
      currentInput.style.boxShadow = '0 0 5px 2px #4285f4';
      currentInput.focus();
      currentInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  removeHighlight() {
    if (this.currentInputIndex >= 0 && this.currentInputIndex < this.formInputs.length) {
      this.formInputs[this.currentInputIndex].style.boxShadow = '';
    }
  }

  sendStatus(text) {
    chrome.runtime.sendMessage({
      type: 'status',
      text: text
    });
  }

  fillCurrentInput(text) {
    if (this.currentInputIndex >= 0 && this.currentInputIndex < this.formInputs.length) {
      const currentInput = this.formInputs[this.currentInputIndex];
      currentInput.value = text;
      currentInput.dispatchEvent(new Event('input', { bubbles: true }));
      currentInput.dispatchEvent(new Event('change', { bubbles: true }));
      this.sendStatus('Filled: ' + text);
    }
  }
}

const formNavigator = new FormNavigator();

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "ping") {
    // Respond to ping to confirm content script is loaded
    formNavigator.initialize();
    sendResponse(true);
    return true;
  } else if (message.action === "startListening") {
    formNavigator.startListening();
    sendResponse(true);
    return true;
  } else if (message.action === "stopListening") {
    formNavigator.stopListening();
    sendResponse(true);
    return true;
  } else if (message.action === "nextInput") {
    formNavigator.moveToNextInput();
    sendResponse(true);
    return true;
  } else if (message.action === "previousInput") {
    formNavigator.moveToPreviousInput();
    sendResponse(true);
    return true;
  }
}); 