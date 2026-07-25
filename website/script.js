// ═══════════════════════════════════════════
//  EchoCore Frontend — script.js
//  Class-based, Flask API connected
// ═══════════════════════════════════════════

const FLASK_BASE = '';   // same origin — Flask serves these files

// ═══════════════════════════════════════════
//  PARTICLE CANVAS
// ═══════════════════════════════════════════
class ParticleField {
  constructor(canvasId) {
    this.canvas  = document.getElementById(canvasId);
    this.ctx     = this.canvas.getContext('2d');
    this.particles = [];
    this.resize();
    this.init();
    window.addEventListener('resize', this._onResize.bind(this));
    requestAnimationFrame(this.loop.bind(this));
  }

  _onResize() {
    clearTimeout(this._resizeTimer);
    this._resizeTimer = setTimeout(() => { this.resize(); this.init(); }, 150);
  }

  resize() {
    this.canvas.width  = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  init() {
    this.particles = [];
    const count = Math.floor((this.canvas.width * this.canvas.height) / 14000);
    for (let i = 0; i < count; i++) {
      this.particles.push({
        x:  Math.random() * this.canvas.width,
        y:  Math.random() * this.canvas.height,
        r:  Math.random() * 1.5 + 0.3,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        a:  Math.random() * 0.5 + 0.2,
      });
    }
  }

  loop() {
    const { ctx, canvas, particles } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = canvas.width;
      if (p.x > canvas.width)  p.x = 0;
      if (p.y < 0) p.y = canvas.height;
      if (p.y > canvas.height) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 207, 255, ${p.a})`;
      ctx.fill();
    }

    // Connection lines
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 100) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(0, 207, 255, ${0.08 * (1 - dist / 100)})`;
          ctx.lineWidth = 0.5;
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(this.loop.bind(this));
  }
}

// ═══════════════════════════════════════════
//  VOICE ASSISTANT
// ═══════════════════════════════════════════
class VoiceAssistant {
  constructor() {
    this.orb      = document.getElementById('echo-orb');
    this.label    = document.getElementById('voice-label');
    this.transcript = document.getElementById('transcript-box');
    this.SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.recognition = null;
  }

  setOrb(state) {
    this.orb.className = 'echo-orb';
    if (state) this.orb.classList.add(state);
  }

  setLabel(text, cls = '') {
    this.label.textContent = text;
    this.label.className   = 'voice-status-label ' + cls;
  }

  start() {
    if (!this.SR) {
      this.setLabel('Voice not supported — use Chrome', 'error');
      return;
    }
    this.recognition = new this.SR();
    this.recognition.lang = 'en-US';
    this.recognition.interimResults = false;
    this.recognition.maxAlternatives = 1;

    this.recognition.onstart = () => {
      this.setOrb('listening');
      this.setLabel('Listening... speak now', 'listening');
    };

    this.recognition.onresult = (e) => {
      const command = e.results[0][0].transcript.toLowerCase();
      this.transcript.textContent = '"' + command + '"';
      this.setOrb('speaking');
      this.processCommand(command);
    };

    this.recognition.onerror = (e) => {
      this.setOrb('');
      this.setLabel('Error: ' + e.error, 'error');
    };

    this.recognition.onend = () => {
      setTimeout(() => {
        this.setOrb('');
        this.setLabel('Ready — press to speak');
      }, 2000);
    };

    this.recognition.start();
  }

  processCommand(cmd) {
    const map = [
      { keywords: ['fan on', 'turn on fan'],      endpoint: '/fan/on',     label: 'Fan turned ON' },
      { keywords: ['fan off', 'turn off fan'],     endpoint: '/fan/off',    label: 'Fan turned OFF' },
      { keywords: ['light on', 'turn on light'],   endpoint: '/led/on',     label: 'Light turned ON' },
      { keywords: ['light off', 'turn off light'], endpoint: '/led/off',    label: 'Light turned OFF' },
      { keywords: ['buzzer on', 'turn on buzzer'], endpoint: '/buzzer/on',  label: 'Buzzer turned ON' },
      { keywords: ['buzzer off','turn off buzzer'],endpoint: '/buzzer/off', label: 'Buzzer turned OFF' },
    ];

    const match = map.find(m => m.keywords.some(k => cmd.includes(k)));
    if (match) {
      EchoCoreApp.cmd(match.endpoint);
      this.setLabel('Done: ' + match.label, 'success');
    } else {
      this.setLabel('Command not recognised', 'error');
    }
  }
}

// ═══════════════════════════════════════════
//  SENSOR DASHBOARD
// ═══════════════════════════════════════════
class SensorDashboard {
  constructor() {
    this.pollInterval = 3000;
    this.timer = null;
  }

  start() {
    this.poll();
    this.timer = setInterval(() => this.poll(), this.pollInterval);
  }

  async poll() {
    try {
      const res  = await fetch(FLASK_BASE + '/sensor');
      const data = await res.json();
      this.update(data);
    } catch (e) {
      console.warn('Sensor poll failed:', e);
    }
  }

  update(d) {
    // Temp / humidity
    this._set('val-temp', d.temp != null ? d.temp.toFixed(1) + ' °C' : '--');
    this._set('val-hum',  d.humidity != null ? d.humidity.toFixed(1) + ' %' : '--');
    this._set('val-gasval', d.gas_val != null ? d.gas_val : '--');

    // Motion
    const motionCard = document.getElementById('card-motion');
    this._set('val-motion',    d.motion ? 'DETECTED' : 'Clear');
    this._set('status-motion', d.motion ? 'Alert' : 'No motion');
    motionCard.className = 'sensor-card ' + (d.motion ? 'alert' : 'ok');

    // Gas
    const gasCard = document.getElementById('card-gas');
    this._set('val-gas',    d.gas ? 'DETECTED' : 'Clear');
    this._set('status-gas', d.gas ? 'Alert' : 'Safe');
    gasCard.className = 'sensor-card ' + (d.gas ? 'alert' : 'ok');

    // Fan
    this._set('val-fan', d.fan ? 'ON' : 'OFF');
    document.getElementById('card-fan').className = 'sensor-card control-card ' + (d.fan ? 'ok' : '');

    // LED
    this._set('val-led', d.clap_led ? 'ON' : 'OFF');
    document.getElementById('card-led').className = 'sensor-card control-card ' + (d.clap_led ? 'ok' : '');

    // Temp card color
    const tempCard = document.getElementById('card-temp');
    if (d.temp != null) tempCard.className = 'sensor-card ' + (d.temp > 35 ? 'alert' : 'ok');

    // Sound level
    const soundVal = d.sound_level || 0;
    this._set('val-sound', soundVal);
    const soundCard = document.getElementById('card-sound');
    soundCard.className = 'sensor-card ' + (soundVal > 2000 ? 'alert' : 'ok');
    this._set('status-sound', soundVal > 2000 ? 'Loud' : 'Normal');

    // Last update
    const now = new Date();
    document.getElementById('last-update-time').textContent =
      now.toLocaleTimeString();
  }

  _set(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }
}

// ═══════════════════════════════════════════
//  SCROLL ANIMATIONS
// ═══════════════════════════════════════════
class ScrollAnimator {
  constructor() {
    this.items = document.querySelectorAll('.fade-up');
    this.io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) e.target.classList.add('visible');
      });
    }, { threshold: 0.12 });
    this.items.forEach(el => this.io.observe(el));
  }
}

// ═══════════════════════════════════════════
//  GSAP ANIMATIONS
// ═══════════════════════════════════════════
function initGSAP() {
  if (typeof gsap === 'undefined') return;

  // Hero entrance
  gsap.from('.wordmark', { duration: 1.4, opacity: 0, y: 40, ease: 'power3.out', delay: 0.3 });
  gsap.from('.tagline',  { duration: 1.2, opacity: 0, y: 20, ease: 'power2.out', delay: 0.8 });
  gsap.from('.hero-cta', { duration: 1,   opacity: 0, y: 20, ease: 'power2.out', delay: 1.1 });
  gsap.from('.orb-hero', { duration: 1.5, opacity: 0, scale: 0.7, ease: 'elastic.out(1, 0.5)', delay: 0.2 });

  // Hero orb floating loop
  gsap.to('.orb-hero', {
    y: -18,
    duration: 3,
    ease: 'sine.inOut',
    yoyo: true,
    repeat: -1,
  });

  // Scroll-triggered sensor cards
  if (typeof ScrollTrigger !== 'undefined') {
    gsap.registerPlugin(ScrollTrigger);
    gsap.from('.sensor-card', {
      scrollTrigger: { trigger: '#dashboard', start: 'top 80%' },
      opacity: 0,
      y: 40,
      stagger: 0.08,
      duration: 0.7,
      ease: 'power2.out',
    });
    gsap.from('#assistant .section-inner > *', {
      scrollTrigger: { trigger: '#assistant', start: 'top 80%' },
      opacity: 0,
      y: 30,
      stagger: 0.1,
      duration: 0.7,
      ease: 'power2.out',
    });
  }
}

// ═══════════════════════════════════════════
//  MAIN APP
// ═══════════════════════════════════════════
const EchoCoreApp = {
  voice:     null,
  dashboard: null,

  async cmd(endpoint) {
    try {
      const res  = await fetch(FLASK_BASE + endpoint);
      const data = await res.json();
      console.log('Command:', endpoint, data);
      // Refresh sensor state immediately
      this.dashboard.poll();
    } catch (e) {
      console.error('Command failed:', endpoint, e);
    }
  },

  async sendWhatsApp() {
    const input = document.getElementById('wa-msg');
    const msg   = input.value.trim();
    if (!msg) return;
    try {
      const res  = await fetch(FLASK_BASE + '/whatsapp', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: msg }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        input.value = '';
        alert('WhatsApp message sent!');
      } else {
        alert('Failed: ' + (data.error || 'unknown error'));
      }
    } catch (e) {
      alert('Could not reach Flask server.');
    }
  },

  init() {
    new ParticleField('particle-canvas');
    this.voice     = new VoiceAssistant();
    this.dashboard = new SensorDashboard();
    this.dashboard.start();
    new ScrollAnimator();
    initGSAP();

    // Clap trigger via SocketIO if available
    if (typeof io !== 'undefined') {
      const socket = io();
      socket.on('clap_detected', () => this.voice.start());
      socket.on('sensor_update', (data) => this.dashboard.update(data));
    }
  },
};

document.addEventListener('DOMContentLoaded', () => EchoCoreApp.init());