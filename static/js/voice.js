/**
 * voice.js — Web Speech API voice-to-text for IntelliBudget AI chatbot.
 *
 * Save as:  static/js/voice.js
 *
 * Add to chatbot.html (before </body>):
 *   <script src="{{ url_for('static', filename='js/voice.js') }}"></script>
 *   <script>
 *     document.addEventListener('DOMContentLoaded', () => {
 *       VoiceInput.init({ inputId: 'messageInput', btnId: 'voiceBtn' });
 *     });
 *   </script>
 *
 * Browser support: Chrome, Edge, Safari 15+
 * Keyboard shortcut: Ctrl + Shift + V
 */

const VoiceInput = (() => {
    'use strict';

    let recognition = null;
    let isListening = false;
    let inputEl     = null;
    let btnEl       = null;
    let statusEl    = null;

    const supported = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

    // ── Build SpeechRecognition instance ────────────────────────────────────
    function _buildRecognition() {
        const SR  = window.SpeechRecognition || window.webkitSpeechRecognition;
        const rec = new SR();

        // Use a locale that works well for Indian English numerals/words.
        rec.lang             = 'en-IN';
        rec.continuous       = false;
        // Interim results often cause "partial" noisy text to be sent.
        // We'll only use final results for reliability.
        rec.interimResults   = false;
        rec.maxAlternatives  = 1;

        rec.onstart = () => {
            isListening = true;
            _setBtn('recording');
            _setStatus('🔴 Listening… speak now', 'danger');
        };

        rec.onresult = (event) => {
            let finalText   = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const t = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalText += t;
                }
            }

            inputEl.value = finalText.trim();

            if (finalText) {
                inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                _setStatus(
                    `✅ Heard: "${finalText.substring(0, 50)}${finalText.length > 50 ? '…' : ''}"`,
                    'success'
                );
            }
        };

        rec.onerror = (event) => {
            isListening = false;
            _setBtn('idle');

            const msgs = {
                'not-allowed':   '🚫 Microphone access denied. Enable it in browser settings.',
                'no-speech':     '🤫 No speech detected. Please try again.',
                'audio-capture': '🎤 No microphone found on this device.',
                'network':       '🌐 Network error during voice recognition.',
            };
            const msg = msgs[event.error] || `Voice error: ${event.error}`;
            _setStatus(msg, 'warning');
            _showToast(msg);
        };

        rec.onend = () => {
            isListening = false;
            _setBtn('idle');

            const val = (inputEl.value || '').trim();
            if (val) {
                // Don't auto-submit. Voice recognition can mis-hear amounts/categories;
                // letting the user review improves correctness.
                _setStatus('✅ Ready. Review and press Send.', 'success');
            } else {
                _setStatus('No speech captured. Try again.', 'muted');
            }
        };

        return rec;
    }

    // ── Button visual states ──────────────────────────────────────────────────
    function _setBtn(state) {
        if (!btnEl) return;

        const cfg = {
            idle: {
                icon:   '🎙️',
                title:  'Click to speak (Ctrl+Shift+V)',
                remove: ['btn-danger', 'btn-outline-danger'],
                add:    'btn-outline-secondary',
            },
            recording: {
                icon:   '🔴',
                title:  'Listening… click to stop',
                remove: ['btn-outline-secondary', 'btn-outline-danger'],
                add:    'btn-danger',
            },
            denied: {
                icon:   '🚫',
                title:  'Microphone unavailable',
                remove: ['btn-outline-secondary', 'btn-danger'],
                add:    'btn-outline-danger',
            },
        };

        const s = cfg[state] || cfg.idle;
        btnEl.innerHTML = s.icon;
        btnEl.title     = s.title;
        s.remove.forEach(c => btnEl.classList.remove(c));
        btnEl.classList.add(s.add);
    }

    // ── Status bar helper ─────────────────────────────────────────────────────
    function _setStatus(msg, colorClass) {
        if (!statusEl) return;
        statusEl.textContent = msg;
        statusEl.className   = `form-text small mt-1 text-${colorClass || 'muted'}`;
    }

    // ── Toast notification ────────────────────────────────────────────────────
    function _showToast(msg, duration = 3500) {
        const t = document.createElement('div');
        t.textContent = msg;
        Object.assign(t.style, {
            position:     'fixed',
            bottom:       '80px',
            left:         '50%',
            transform:    'translateX(-50%)',
            background:   '#1e293b',
            color:        '#f1f5f9',
            padding:      '8px 20px',
            borderRadius: '20px',
            fontSize:     '13px',
            zIndex:       '9999',
            boxShadow:    '0 4px 16px rgba(0,0,0,.35)',
            whiteSpace:   'nowrap',
        });
        document.body.appendChild(t);
        setTimeout(() => t.remove(), duration);
    }

    // ── Public API ─────────────────────────────────────────────────────────────
    function init({ inputId = 'messageInput', btnId = 'voiceBtn', statusId = 'voiceStatus' } = {}) {
        inputEl  = document.getElementById(inputId);
        btnEl    = document.getElementById(btnId);
        statusEl = document.getElementById(statusId);

        if (!inputEl || !btnEl) {
            console.warn('[VoiceInput] Elements not found:', inputId, btnId);
            return;
        }

        if (!supported) {
            _setBtn('denied');
            btnEl.disabled = true;
            _setStatus('⚠️ Voice input not supported. Use Chrome, Edge, or Safari.', 'warning');
            return;
        }

        recognition = _buildRecognition();

        btnEl.addEventListener('click', (e) => {
            e.preventDefault();
            if (isListening) {
                recognition.stop();
            } else {
                // Keep existing text; users often want to append/correct.
                try {
                    recognition.start();
                } catch (err) {
                    // Recognition already started — ignore
                }
            }
        });

        // Keyboard shortcut: Ctrl + Shift + V
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.shiftKey && (e.key === 'V' || e.key === 'v')) {
                e.preventDefault();
                btnEl.click();
            }
        });

        console.log('[VoiceInput] Ready. Shortcut: Ctrl+Shift+V');
    }

    return { init, supported };
})();
