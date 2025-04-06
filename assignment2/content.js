// Function to extract main content from the webpage
function extractPageContent() {
  // Get the main news content and person
  const { newsContent, mainPerson } = findNewsContent();

  return {
    mainPerson,
    newsContent,
    url: window.location.href,
    title: document.title
  };
}

function findNewsContent() {
  let mainPerson = null;
  let newsContent = '';

  // Try to find article content first
  const article = document.querySelector('article');
  if (article) {
    const headline = article.querySelector('h1, h2');
    if (headline) {
      mainPerson = extractPersonName(headline.textContent);
      newsContent = article.textContent;
    }
  }

  // If no article found, try common news site selectors
  if (!newsContent) {
    // Try to find the main headline
    const headline = document.querySelector('.headline, .article-title, .story-title, h1');
    if (headline) {
      mainPerson = extractPersonName(headline.textContent);
    }

    // Try to find the main content
    const contentSelectors = [
      '.article-content',
      '.story-content',
      '.news-content',
      'main',
      '[role="main"]',
      '.main-content'
    ];

    for (const selector of contentSelectors) {
      const content = document.querySelector(selector);
      if (content) {
        newsContent = content.textContent;
        break;
      }
    }
  }

  // If still no content, get visible text from paragraphs
  if (!newsContent) {
    const paragraphs = Array.from(document.getElementsByTagName('p'))
      .filter(p => {
        const style = window.getComputedStyle(p);
        return style.display !== 'none' && style.visibility !== 'hidden' && p.textContent.trim().length > 50;
      })
      .map(p => p.textContent.trim())
      .join(' ');
    
    if (paragraphs) {
      newsContent = paragraphs;
    }
  }

  // Clean up the content
  newsContent = cleanContent(newsContent || document.body.textContent);

  return {
    newsContent,
    mainPerson: mainPerson || findPersonInContent(newsContent)
  };
}

function extractPersonName(text) {
  // Look for patterns like "FirstName LastName"
  const matches = text.match(/[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+/);
  return matches ? matches[0] : null;
}

function findPersonInContent(content) {
  // Look for person names in the first few sentences
  const sentences = content.split(/[.!?]+/).slice(0, 3);
  for (const sentence of sentences) {
    const name = extractPersonName(sentence);
    if (name) return name;
  }
  return null;
}

function cleanContent(text) {
  return text
    .trim()
    .replace(/\s+/g, ' ')        // Replace multiple spaces with single space
    .replace(/[^\w\s.,!?-]/g, '') // Remove special characters except basic punctuation
    .substring(0, 500);          // Limit length
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getPageContent") {
    sendResponse(extractPageContent());
  }
}); 