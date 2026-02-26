/**
 * Voice UI components — mic button, recording indicator, mode toggle, volume slider.
 * Integrates into existing chat input areas.
 */
import { voiceManager } from './voice.js';

let _uiElements = null;

const MIC_ICON_SVG = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>`;

export function initVoiceUI(chatInputForm, animaName) {
  if (_uiElements) destroyVoiceUI();

  const container = document.createElement('div');
  container.className = 'voice-controls';

  const micBtn = document.createElement('button');
  micBtn.type = 'button';
  micBtn.className = 'voice-mic-btn';
  micBtn.title = '音声入力';
  micBtn.innerHTML = MIC_ICON_SVG;

  const recIndicator = document.createElement('span');
  recIndicator.className = 'voice-rec-indicator';
  recIndicator.style.display = 'none';

  const ttsIndicator = document.createElement('span');
  ttsIndicator.className = 'voice-tts-indicator';
  ttsIndicator.style.display = 'none';

  const modeToggle = document.createElement('button');
  modeToggle.type = 'button';
  modeToggle.className = 'voice-mode-toggle';
  modeToggle.textContent = 'PTT';
  modeToggle.title = '入力モード切替（PTT/自動）';
  modeToggle.style.display = 'none';

  const volumeSlider = document.createElement('input');
  volumeSlider.type = 'range';
  volumeSlider.className = 'voice-volume-slider';
  volumeSlider.min = '0';
  volumeSlider.max = '100';
  volumeSlider.value = '80';
  volumeSlider.style.display = 'none';

  container.append(micBtn, recIndicator, ttsIndicator, modeToggle, volumeSlider);

  const sendBtn = chatInputForm.querySelector(
    '[id$="SendBtn"], .chat-send-btn, button[type="submit"]'
  );
  if (sendBtn) {
    chatInputForm.insertBefore(container, sendBtn);
  } else {
    chatInputForm.appendChild(container);
  }

  _uiElements = {
    container,
    micBtn,
    recIndicator,
    ttsIndicator,
    modeToggle,
    volumeSlider,
  };

  let voiceActive = false;

  micBtn.addEventListener('click', async () => {
    if (!voiceActive) {
      await voiceManager.connect(animaName);
      voiceActive = true;
      micBtn.classList.add('active');
      modeToggle.style.display = '';
      volumeSlider.style.display = '';
    } else if (voiceManager.mode === 'ptt') {
      if (voiceManager.isRecording) {
        voiceManager.stopRecording();
      } else {
        voiceManager.startRecording();
      }
    }
  });

  micBtn.addEventListener('mousedown', (e) => {
    if (voiceActive && voiceManager.mode === 'ptt' && e.button === 0) {
      voiceManager.startRecording();
    }
  });
  micBtn.addEventListener('mouseup', () => {
    if (voiceActive && voiceManager.mode === 'ptt' && voiceManager.isRecording) {
      voiceManager.stopRecording();
    }
  });
  micBtn.addEventListener('mouseleave', () => {
    if (voiceActive && voiceManager.mode === 'ptt' && voiceManager.isRecording) {
      voiceManager.stopRecording();
    }
  });

  modeToggle.addEventListener('click', () => {
    const newMode = voiceManager.mode === 'ptt' ? 'vad' : 'ptt';
    voiceManager.setMode(newMode);
    modeToggle.textContent = newMode === 'ptt' ? 'PTT' : 'AUTO';
  });

  volumeSlider.addEventListener('input', () => {
    voiceManager.setVolume(parseInt(volumeSlider.value, 10) / 100);
  });

  voiceManager.on('recordingStart', () => {
    recIndicator.style.display = '';
    micBtn.classList.add('recording');
  });
  voiceManager.on('recordingStop', () => {
    recIndicator.style.display = 'none';
    micBtn.classList.remove('recording');
  });
  voiceManager.on('ttsStart', () => {
    ttsIndicator.style.display = '';
  });
  voiceManager.on('ttsDone', () => {
    if (!voiceManager.isTTSPlaying) ttsIndicator.style.display = 'none';
  });
  voiceManager.on('playbackEnd', () => {
    ttsIndicator.style.display = 'none';
  });
  voiceManager.on('disconnected', () => {
    voiceActive = false;
    micBtn.classList.remove('active', 'recording');
    recIndicator.style.display = 'none';
    ttsIndicator.style.display = 'none';
    modeToggle.style.display = 'none';
    volumeSlider.style.display = 'none';
  });
  voiceManager.on('error', ({ message }) => {
    console.warn('[VoiceUI] Error:', message);
  });

  return _uiElements;
}

export function destroyVoiceUI() {
  if (_uiElements) {
    voiceManager.disconnect();
    _uiElements.container.remove();
    _uiElements = null;
  }
}

export function updateVoiceUIAnima(animaName) {
  if (voiceManager.isConnected) {
    voiceManager.disconnect();
  }
}
