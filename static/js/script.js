function fetchLiveData(lat, lon) {
  fetch(`/live?lat=${lat}&lon=${lon}`)
    .then(response => {
      if (!response.ok) throw new Error('Fetch failed');
      return response.json();
    })
    .then(data => {
      localStorage.setItem('lastLiveData', JSON.stringify(data));
      document.getElementById('live-data').innerHTML = `
        <h3>Live Solar Data</h3>
        <p>Temperature: ${data.temperature || 'N/A'}°C</p>
        <p>Wind Speed: ${data.windspeed || 'N/A'} m/s</p>`;
    })
    .catch(error => {
      console.error('Fetch Live Data Error:', error);
      const cachedLive = localStorage.getItem('lastLiveData');
      document.getElementById('live-data').innerHTML = cachedLive ? 
        `<h3>Live Solar Data (Cached)</h3><p>Temperature: ${JSON.parse(cachedLive).temperature || 'N/A'}°C</p><p>Wind Speed: ${JSON.parse(cachedLive).windspeed || 'N/A'} m/s</p>` : 
        '<p>Live data unavailable</p>';
    });
}

function shareResults(score, badge, place) {
  const text = `My ${place} solar score is ${score}! I'm a ${badge} with JuaNuru.`;
  navigator.clipboard.writeText(text);
  alert('Copied to clipboard: ' + text);
}