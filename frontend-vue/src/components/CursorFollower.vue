<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue';

const ringEl = ref(null);
const dotEl = ref(null);
let raf = 0;
let mouseX = 0;
let mouseY = 0;
let ringX = 0;
let ringY = 0;
const TARGETS =
  'button, a, [data-task-id], .feature-card, .file-drop, input, select, .nav-item, .captcha-image, .workflow-step';

function onMove(e) {
  mouseX = e.clientX;
  mouseY = e.clientY;
  if (dotEl.value) {
    dotEl.value.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-50%, -50%)`;
    dotEl.value.classList.add('active');
  }
  if (ringEl.value) ringEl.value.classList.add('active');
}

function onLeave() {
  ringEl.value?.classList.remove('active');
  dotEl.value?.classList.remove('active');
}

function onOver(e) {
  if (e.target.closest(TARGETS)) ringEl.value?.classList.add('hover');
}

function onOut(e) {
  if (e.target.closest(TARGETS)) ringEl.value?.classList.remove('hover');
}

function animate() {
  ringX += (mouseX - ringX) * 0.18;
  ringY += (mouseY - ringY) * 0.18;
  if (ringEl.value) {
    ringEl.value.style.transform = `translate(${ringX}px, ${ringY}px) translate(-50%, -50%)`;
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
  raf = requestAnimationFrame(animate);
});

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onMove);
  document.removeEventListener('mouseleave', onLeave);
  document.removeEventListener('mouseover', onOver);
  document.removeEventListener('mouseout', onOut);
  if (raf) cancelAnimationFrame(raf);
});
</script>

<template>
  <div ref="ringEl" class="cursor-ring"></div>
  <div ref="dotEl" class="cursor-dot"></div>
</template>
