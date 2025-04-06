document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('fetchData').addEventListener('click', async () => {
        try {
            const query = document.getElementById('queryInput').value.trim();
            
            const response = await fetch('http://localhost:8000/parking_query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ query: query })
            });

            const data = await response.json();
            
            // Display the text response
            document.getElementById('text-response').textContent = data.text_response;

            // Only create and display the plot if graphical data is available
            if (data.graphical_data && data.graphical_data.data) {
                // Create the plot with all traces from the data
                Plotly.newPlot('plot', data.graphical_data.data, data.graphical_data.layout);
            } else {
                // Clear the plot if no graphical data is available
                const plotDiv = document.getElementById('plot');
                plotDiv.innerHTML = '';
            }
        } catch (error) {
            console.error('Error fetching data:', error);
            document.getElementById('text-response').textContent = 'Error fetching data. Please make sure the server is running.';
        }
    });
}); 