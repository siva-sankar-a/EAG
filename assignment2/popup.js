document.addEventListener('DOMContentLoaded', () => {
  const generateButton = document.getElementById('generateMeme');
  const loadingIndicator = document.getElementById('loadingIndicator');
  const memeContainer = document.getElementById('memeContainer');
  const memeImage = document.getElementById('memeImage');
  const errorMessage = document.getElementById('errorMessage');

  const GEMINI_API_KEY = 'YOUR_API_KEY'; // Replace with your API key
  const GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent';
  const MEME_API_ENDPOINT = 'https://api.memegen.link';

  let memeTemplates = [];

  // Fetch meme templates when popup opens
  async function fetchMemeTemplates() {
    try {
      const response = await fetch(`${MEME_API_ENDPOINT}/templates`);
      if (!response.ok) throw new Error('Failed to fetch meme templates');
      memeTemplates = await response.json();
      console.log('Loaded meme templates:', memeTemplates.length);
    } catch (error) {
      console.error('Error fetching templates:', error);
      throw new Error('Failed to load meme templates');
    }
  }

  function cleanJsonResponse(text) {
    // Remove markdown code block formatting if present
    return text.replace(/^```json\n/, '')  // Remove opening ```json
              .replace(/\n```$/, '')       // Remove closing ```
              .trim();                     // Clean up whitespace
  }

  async function analyzeContent(text) {
    const response = await fetch(`${GEMINI_ENDPOINT}?key=${GEMINI_API_KEY}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        contents: [{
          parts: [{
            text: `Extract the main person/subject and key news from this text. If you can't find them, respond with "no_content".
            
            Text: ${text}
            
            Respond with ONLY this JSON (no markdown, no code blocks):
            {
              "mainPerson": "person name or subject",
              "mainNews": "brief description of the key news"
            }`
          }]
        }]
      })
    });

    if (!response.ok) {
      throw new Error('Failed to analyze content');
    }

    const data = await response.json();
    const textResponse = cleanJsonResponse(data.candidates[0].content.parts[0].text);
    
    try {
      const parsed = JSON.parse(textResponse);
      // Check if we got meaningful content
      if (parsed.mainPerson.includes("Unclear") || parsed.mainPerson === "no_content") {
        throw new Error('No meaningful content found on the page');
      }
      return parsed;
    } catch (e) {
      console.error('Failed to parse response:', textResponse);
      throw new Error('Could not extract content from the page');
    }
  }

  async function generateMemeIdea(person, news) {
    const response = await fetch(`${GEMINI_ENDPOINT}?key=${GEMINI_API_KEY}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        contents: [{
          parts: [{
            text: `Create a funny meme about "${person}" related to this news: "${news}"
            Choose from these meme templates: ${memeTemplates.slice(0, 10).map(t => `${t.name} (id: ${t.id})`).join(', ')}
            
            Respond with ONLY this JSON (no markdown, no code blocks):
            {
              "template_id": "choose a template ID from the list above",
              "topText": "text for top of meme (keep it short)",
              "bottomText": "text for bottom of meme (keep it short)"
            }`
          }]
        }]
      })
    });

    if (!response.ok) {
      throw new Error('Failed to generate meme idea');
    }

    const data = await response.json();
    const textResponse = cleanJsonResponse(data.candidates[0].content.parts[0].text);
    
    try {
      return JSON.parse(textResponse);
    } catch (e) {
      console.error('Failed to parse response:', textResponse);
      throw new Error('Failed to generate meme concept');
    }
  }

  async function createMeme(template_id, topText, bottomText) {
    try {
      console.log('Creating meme with:', { template_id, text: [topText, bottomText] });
      
      const response = await fetch(`${MEME_API_ENDPOINT}/images`, {
        method: 'POST',
        headers: {
          'accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          template_id: template_id,
          text: [
            topText || ' ',  // Use space if empty to prevent API errors
            bottomText || ' ' // Use space if empty to prevent API errors
          ]
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Meme API error:', errorText);
        throw new Error(`Failed to create meme: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      console.log('Meme API response:', data);
      
      if (!data.url) {
        throw new Error('No URL in meme response');
      }
      
      return data.url;
    } catch (error) {
      console.error('Error creating meme:', error);
      throw new Error(`Failed to create meme: ${error.message}`);
    }
  }

  generateButton.addEventListener('click', async () => {
    try {
      // Show loading indicator
      loadingIndicator.classList.remove('hidden');
      memeContainer.classList.add('hidden');
      errorMessage.classList.add('hidden');

      // Make sure we have templates loaded
      if (memeTemplates.length === 0) {
        await fetchMemeTemplates();
      }

      // Get the current tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      // Get page content from content script
      const content = await chrome.tabs.sendMessage(tab.id, { action: "getPageContent" });

      // First analyze the content to extract person and news
      const analysis = await analyzeContent(content.newsContent);
      console.log('Content analysis:', analysis);

      // Then generate the meme concept
      const memeIdea = await generateMemeIdea(analysis.mainPerson, analysis.mainNews);
      console.log('Meme idea:', memeIdea);

      // Create the actual meme
      const memeUrl = await createMeme(
        memeIdea.template_id,
        memeIdea.topText,
        memeIdea.bottomText
      );
      
      // Display the generated meme
      memeImage.src = memeUrl;
      memeContainer.classList.remove('hidden');
    } catch (error) {
      errorMessage.textContent = `Error: ${error.message}`;
      errorMessage.classList.remove('hidden');
      console.error('Error:', error);
    } finally {
      loadingIndicator.classList.add('hidden');
    }
  });

  // Fetch templates when popup opens
  fetchMemeTemplates().catch(error => {
    errorMessage.textContent = `Error: ${error.message}`;
    errorMessage.classList.remove('hidden');
  });
}); 