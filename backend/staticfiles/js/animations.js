/**
 * Expenzo High-Performance Animations Engine
 * Optimized for 60fps GPU rendering, FOUC elimination, and battery/CPU conservation
 */
(function() {
  'use strict';

  // 1. Wait for Window Load + Web Fonts Ready to eliminate FOUC and layout shift
  function waitForReady() {
    return new Promise(function(resolve) {
      function onReady() {
        if (document.fonts && document.fonts.ready) {
          document.fonts.ready.then(resolve).catch(resolve);
        } else {
          resolve();
        }
      }
      if (document.readyState === 'complete') {
        onReady();
      } else {
        window.addEventListener('load', onReady, { once: true });
      }
    });
  }

  // 2. Subtle pulse hover effect for interactive elements (GPU-only will-change lifecycle)
  function initButtonHoverEffects() {
    const interactiveSelectors = [
      'button:not([disabled])',
      '.btn',
      '.sidebar-toggle-btn',
      '.sidebar-collapse-btn',
      '.hamburger-btn',
      '.topbar-user-pill',
      '.personal-spend-nav-pill'
    ];

    const elements = document.querySelectorAll(interactiveSelectors.join(', '));
    elements.forEach(function(el) {
      if (el.dataset.hasPulseHover === 'true') return;
      el.dataset.hasPulseHover = 'true';

      el.addEventListener('mouseenter', function() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        if (el.classList.contains('animate__pulse')) return;

        // Apply will-change strictly for the duration of the hover pulse
        el.style.willChange = 'transform';
        el.style.setProperty('--animate-duration', '0.4s');
        el.classList.add('animate__animated', 'animate__pulse');

        function onEnd() {
          el.classList.remove('animate__animated', 'animate__pulse');
          el.style.willChange = '';
          el.style.removeProperty('--animate-duration');
          el.removeEventListener('animationend', onEnd);
        }
        el.addEventListener('animationend', onEnd, { once: true });
      });
    });
  }

  // 3. High-performance scroll reveal using IntersectionObserver (threshold 0.15)
  function initScrollReveal() {
    const revealElements = document.querySelectorAll('.reveal');
    if (revealElements.length === 0) return;

    if (!('IntersectionObserver' in window)) {
      revealElements.forEach(function(el) {
        el.classList.remove('reveal');
        const effect = el.getAttribute('data-reveal') || 'animate__fadeInUp';
        el.classList.add('animate__animated', effect);
      });
      return;
    }

    const observer = new IntersectionObserver(function(entries, obs) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          const el = entry.target;
          const effect = el.getAttribute('data-reveal') || 'animate__fadeInUp';
          el.classList.remove('reveal');
          // Isolate to GPU layer only while entering
          el.style.willChange = 'transform, opacity';
          el.classList.add('animate__animated', effect);

          el.addEventListener('animationend', function() {
            el.classList.remove('animate__animated', effect);
            el.style.willChange = '';
          }, { once: true });

          obs.unobserve(el);
        }
      });
    }, {
      threshold: 0.15,
      rootMargin: '0px 0px -40px 0px'
    });

    revealElements.forEach(function(el) {
      observer.observe(el);
    });
  }

  // 4. Entrance animation cleanup and dynamic will-change removal
  function initEntranceCleanup() {
    const animatedElements = document.querySelectorAll('.animate__animated:not(.animate__pulse)');
    animatedElements.forEach(function(el) {
      if (el.dataset.hasAnimCleanup === 'true') return;
      el.dataset.hasAnimCleanup = 'true';

      // Promote to compositor layer only while animating
      el.style.willChange = 'transform, opacity';

      el.addEventListener('animationend', function() {
        el.style.willChange = '';
        const effects = [
          'animate__animated',
          'animate__fadeIn',
          'animate__fadeInDown',
          'animate__fadeInLeft',
          'animate__fadeInUp',
          'animate__zoomIn'
        ];
        effects.forEach(function(cls) {
          el.classList.remove(cls);
        });
        el.style.removeProperty('--animate-delay');
        el.style.removeProperty('--animate-duration');
      }, { once: true });
    });
  }

  // 5. Modal entrance animation using MutationObserver
  function initModalAnimations() {
    const modals = document.querySelectorAll('.modal-overlay');
    modals.forEach(function(modal) {
      if (modal.dataset.hasAnimObserver === 'true') return;
      modal.dataset.hasAnimObserver = 'true';

      let prevDisplay = window.getComputedStyle(modal).display;

      const observer = new MutationObserver(function() {
        const currentDisplay = window.getComputedStyle(modal).display;
        if (prevDisplay === 'none' && currentDisplay !== 'none') {
          const content = modal.querySelector('.modal-content');
          if (content) {
            content.classList.remove('animate__animated', 'animate__zoomIn', 'animate__zoomOut');
            content.style.willChange = 'transform, opacity';
            content.style.setProperty('--animate-duration', '0.3s');
            content.classList.add('animate__animated', 'animate__zoomIn');
            content.addEventListener('animationend', function() {
              content.classList.remove('animate__animated', 'animate__zoomIn');
              content.style.willChange = '';
              content.style.removeProperty('--animate-duration');
            }, { once: true });
          }
        }
        prevDisplay = currentDisplay;
      });

      observer.observe(modal, { attributes: true, attributeFilter: ['style', 'class'] });
    });
  }

  function startAllAnimations() {
    // Reveal animated elements cleanly now that fonts and DOM are ready
    if (document.documentElement) {
      document.documentElement.classList.remove('wf-loading');
    }
    initButtonHoverEffects();
    initScrollReveal();
    initEntranceCleanup();
    initModalAnimations();
  }

  window.initExpenzoAnimations = startAllAnimations;

  // Execute sequence: wait for window.onload AND document.fonts.ready
  waitForReady().then(startAllAnimations);
})();
