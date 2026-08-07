// Simple test
console.log('Test script loaded');
fetch('/api/maps')
    .then(r => r.json())
    .then(d => console.log('Maps:', d.data.length))
    .catch(e => console.error('Error:', e));
