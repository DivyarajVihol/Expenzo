/**
 * Expenzo Professional Subtle Animations Manager
 * Powered by Animate.css v4.1.1
 */
(function() {
  'use strict';

  function initButtonHoverEffects() {
    // Subtle pulse on hover for buttons, navigation tabs, and icon actions
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

        el.style.setProperty('--animate-duration', '0.4s');
        el.classList.add('animate__animated', 'animate__pulse');

        function onEnd() {
          el.classList.remove('animate__animated', 'animate__pulse');
          el.style.removeProperty('--animate-duration');
          el.removeEventListener('animationend', onEnd);
        }
        el.addEventListener('animationend', onEnd, { once: true });
      });
    });
  }

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
          el.classList.add('animate__animated', effect);

          el.addEventListener('animationend', function() {
            el.classList.remove('animate__animated', effect);
          }, { once: true });

          obs.unobserve(el);
        }
      });
    }, {
      threshold: 0.15
    });

    revealElements.forEach(function(el) {
      observer.observe(el);
    });
  }

  function initEntranceCleanup() {
    // Automatically clean up entrance animation classes once animation completes
    // so no lingering transform or opacity overrides conflict with cards, hover, or layout
    const animatedElements = document.querySelectorAll('.animate__animated:not(.animate__pulse)');
    animatedElements.forEach(function(el) {
      if (el.dataset.hasAnimCleanup === 'true') return;
      el.dataset.hasAnimCleanup = 'true';

      el.addEventListener('animationend', function() {
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

  function initModalAnimations() {
    const modals = document.querySelectorAll('.modal-overlay');
    modals.forEach(function(modal) {
      if (modal.dataset.hasAnimObserver === 'true') return;
      modal.dataset.hasAnimObserver = 'true';

      let prevDisplay = window.getComputedStyle(modal).display;

      const observer = new MutationObserver(function() {
        const currentDisplay = window.getComputedStyle(modal).display;
        if (prevDisplay === 'none' && currentDisplay !== 'none') {
          // Modal opened -> subtle zoomIn on modal-content
          const content = modal.querySelector('.modal-content');
          if (content) {
            content.classList.remove('animate__animated', 'animate__zoomIn', 'animate__zoomOut');
            content.style.setProperty('--animate-duration', '0.35s');
            content.classList.add('animate__animated', 'animate__zoomIn');
            content.addEventListener('animationend', function() {
              content.classList.remove('animate__animated', 'animate__zoomIn');
              content.style.removeProperty('--animate-duration');
            }, { once: true });
          }
        }
        prevDisplay = currentDisplay;
      });

      observer.observe(modal, { attributes: true, attributeFilter: ['style', 'class'] });
    });
  }

  function initAllAnimations() {
    initButtonHoverEffects();
    initScrollReveal();
    initEntranceCleanup();
    initModalAnimations();
  }

  window.initExpenzoAnimations = initAllAnimations;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAllAnimations);
  } else {
    initAllAnimations();
  }
})();
