function fetchLiveData(lat, lon) {
  fetch(`/live?lat=${lat}&lon=${lon}`)
      .then(response => response.json())
      .then(data => {
          document.getElementById('live-data').innerHTML = `
              <h3>Live Solar Data</h3>
              <p>Temperature: ${data.temperature}°C</p>
              <p>Wind Speed: ${data.windspeed} m/s</p>`;
      });
}

function shareResults(score, badge, place) {
  const text = `My ${place} solar score is ${score}! I'm a ${badge} with JuaNuru.`;
  navigator.clipboard.writeText(text);
  alert('Copied to clipboard: ' + text);
}

document.getElementById('voice-btn').addEventListener('click', () => {
  const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
  recognition.onresult = (event) => {
      document.getElementById('place').value = event.results[0][0].transcript;
  };
  recognition.start();
});

document.getElementById('system-size').addEventListener('input', function() {
  const size = this.value;
  const cost = size * 5;
  document.getElementById('monthly-cost').textContent = cost;
});