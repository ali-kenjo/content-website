// Dark mode toggle functionality
const darkModeToggle = document.querySelector('.dark-mode-toggle');
const html = document.documentElement;

// Check for saved dark mode preference or system preference
function initDarkMode() {
  const savedPreference = localStorage.getItem('darkMode');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  const isDarkMode = savedPreference === 'true' || (savedPreference === null && prefersDark);
  
  if (isDarkMode) {
    html.classList.add('dark-mode');
    updateButtonText(true);
  }
}

// Toggle dark mode
function toggleDarkMode() {
  html.classList.toggle('dark-mode');
  const isDarkMode = html.classList.contains('dark-mode');
  localStorage.setItem('darkMode', isDarkMode);
  updateButtonText(isDarkMode);
}

// Update button text
function updateButtonText(isDarkMode) {
  if (darkModeToggle) {
    darkModeToggle.textContent = isDarkMode ? '☀️ Light' : '🌙 Dark';
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initDarkMode);

// Add click listener to toggle button
if (darkModeToggle) {
  darkModeToggle.addEventListener('click', toggleDarkMode);
}
