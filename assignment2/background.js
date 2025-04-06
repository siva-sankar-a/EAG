// Background script to handle any background tasks
chrome.runtime.onInstalled.addListener(() => {
  console.log('Meme Generator Extension installed');
});

// You can add more background functionality here if needed 