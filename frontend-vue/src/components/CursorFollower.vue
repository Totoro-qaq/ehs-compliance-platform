<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue';

const ringEl = ref(null);
const dotEl = ref(null);
const glowEl = ref(null);
let raf = 0;
let mouseX = 0;
let mouseY = 0;
let ringX = 0;
let ringY = 0;
let glowX = 0;
let glowY = 0;
let sampleFrame = 0;
const TARGETS =
  'button, a, [data-task-id], .feature-card, .file-drop, .nav-item, .captcha-image, .workflow-step, .quick-action, .recent-item, .scenario-card, .proof-card, .report-preview-shell';
const TEXT_TARGETS = 'input, textarea, select, [contenteditable="true"]';

function onMove(e) {
  mouseX = e.clientX;
  mouseY = e.clientY;
  if (dotEl.value) {
    dotEl.value.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-50%, -50%)`;
    dotEl.value.classList.add('active');
  }
  if (ringEl.value) ringEl.value.classList.add('active');
  if (glowEl.value) glowEl.value.classList.add('active');
  if (!sampleFrame) sampleFrame = requestAnimationFrame(updateTone);
}

function onLeave() {
  ringEl.value?.classList.remove('active');
  dotEl.value?.classList.remove('active');
  glowEl.value?.classList.remove('active');
}

function onOver(e) {
  if (e.target.closest(TEXT_TARGETS)) {
    ringEl.value?.classList.add('text');
    dotEl.value?.classList.add('text');
    glowEl.value?.classList.remove('hover');
    return;
  }
  if (e.target.closest(TARGETS)) {
    ringEl.value?.classList.add('hover');
    glowEl.value?.classList.add('hover');
  }
}

function onOut(e) {
  if (e.target.closest(TEXT_TARGETS)) {
    ringEl.value?.classList.remove('text');
    dotEl.value?.classList.remove('text');
  }
  if (e.target.closest(TARGETS)) {
    ringEl.value?.classList.remove('hover');
    glowEl.value?.classList.remove('hover');
  }
}

function onDown() {
  ringEl.value?.classList.add('press');
  dotEl.value?.classList.add('press');
  glowEl.value?.classList.add('press');
}

function onUp() {
  ringEl.value?.classList.remove('press');
  dotEl.value?.classList.remove('press');
  glowEl.value?.classList.remove('press');
}

function parseColor(value) {
  const match = value?.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function isTransparent(value) {
  return !value || value === 'transparent' || value === 'rgba(0, 0, 0, 0)';
}

function updateTone() {
  sampleFrame = 0;
  const hidden = [ringEl.value, dotEl.value, glowEl.value].filter(Boolean);
  hidden.forEach((el) => {
    el.style.visibility = 'hidden';
  });
  const below = document.elementFromPoint(mouseX, mouseY);
  hidden.forEach((el) => {
    el.style.visibility = '';
  });

  let el = below;
  let color = null;
  while (el && el !== document.documentElement) {
    const bg = getComputedStyle(el).backgroundColor;
    if (!isTransparent(bg)) {
      color = parseColor(bg);
      break;
    }
    el = el.parentElement;
  }

  const [r, g, b] = color || [249, 250, 251];
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  const dark = luminance < 0.42 || below?.closest?.('.intelligence-section, .hero-product-preview');
  for (const cursorEl of hidden) {
    cursorEl.classList.toggle('on-dark', Boolean(dark));
  }
}

function animate() {
  ringX += (mouseX - ringX) * 0.22;
  ringY += (mouseY - ringY) * 0.22;
  glowX += (mouseX - glowX) * 0.12;
  glowY += (mouseY - glowY) * 0.12;
  if (ringEl.value) {
    ringEl.value.style.transform = `translate(${ringX}px, ${ringY}px) translate(-50%, -50%)`;
  }
  if (glowEl.value) {
    glowEl.value.style.transform = `translate(${glowX}px, ${glowY}px) translate(-50%, -50%)`;
  }
  raf = requestAnimationFrame(animate);
}

onMounted(() => {
  if (matchMedia('(hover: none)').matches) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseleave', onLeave);
  document.addEventListener('mouseover', onOver);
  document.addEventListener('mouseout', onOut);
  document.addEventListener('mousedown', onDown);
  document.addEventListener('mouseup', onUp);
  raf = requestAnimationFrame(animate);
});

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onMove);
  document.removeEventListener('mouseleave', onLeave);
  document.removeEventListener('mouseover', onOver);
  document.removeEventListener('mouseout', onOut);
  document.removeEventListener('mousedown', onDown);
  document.removeEventListener('mouseup', onUp);
  if (raf) cancelAnimationFrame(raf);
  if (sampleFrame) cancelAnimationFrame(sampleFrame);
});
</script>

<template>
  <div ref="glowEl" class="cursor-glow"></div>
  <div ref="ringEl" class="cursor-ring"></div>
  <div ref="dotEl" class="cursor-dot"></div>
</template>
